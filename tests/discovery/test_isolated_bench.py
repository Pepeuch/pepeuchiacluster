"""Offline guard tests; real Docker experiments require the explicit VM mission."""

from copy import deepcopy
import io
import json
from pathlib import Path
import secrets
import struct
import unittest
from unittest.mock import patch

import isolated_bench_clients as clients
import isolated_docker_bench as controller
from isolated_bench_workload import SIZES, TABLES, corpus, expected, normalize, pg_load, queries, sql_batches, surreal_load


class Corpus(unittest.TestCase):
    def setUp(self):
        for target in ("socket.create_connection", "socket.socket.connect", "socket.getaddrinfo", "subprocess.Popen"):
            guard = patch(target, side_effect=AssertionError("Offline guard test"))
            guard.start()
            self.addCleanup(guard.stop)

    def test_authorized_sizes_only_and_deterministic_data(self):
        for size in SIZES:
            data = corpus(size)
            self.assertEqual(len(data["model"]), size)
            self.assertEqual(data["data_kind"], "synthetic")
            self.assertEqual(data, corpus(size))
        for size in (0, True, 100000, -1):
            with self.assertRaises(ValueError):
                corpus(size)

    def test_literal_reduced_reference_for_relations_costs_roles_and_benchmarks(self):
        result = expected(corpus(30))
        self.assertEqual(result["provider_filter"], [{"model_id": "m00001"}, {"model_id": "m00009"}, {"model_id": "m00017"}, {"model_id": "m00025"}])
        self.assertEqual(result["runtime_gpu"][:3], [{"model_id": "m00001"}, {"model_id": "m00003"}, {"model_id": "m00009"}])
        self.assertEqual(result["base_quant"][0], {"model_id": "m00001", "base_model": "m00000", "quant": "f16"})
        self.assertEqual(result["provider_cost"][0], {"model_id": "m00000", "provider_id": "p0", "input_cost": .1})
        self.assertEqual(result["local_benchmark"][0], {"model_id": "m00014", "score": 98})
        self.assertEqual(result["role_candidate"][0], {"model_id": "m00008"})

    def test_graph_links_are_explicit_valid_and_quantization_compatible(self):
        data = corpus(1000)
        models = {m["model_id"] for m in data["model"]}
        variants = {v["variant_id"]: v for v in data["variant"]}
        for model in data["model"]:
            self.assertTrue(model["base_id"] is None or model["base_id"] in models)
        for edge in data["fits"]:
            self.assertLessEqual(variants[edge["variant_id"]]["vram_gb"], 12 if edge["gpu_id"]=="g0" else 24)
        self.assertEqual(len({e["edge_id"] for e in data["supports"]}), 1000)

    def test_vector_reference_scores_independently_satisfy_cosine_bounds_and_ties(self):
        data = corpus(1000)
        rows = expected(data)
        for name in ("vector_exact", "hybrid_exact"):
            self.assertEqual(len(rows[name]), 10)
            self.assertTrue(all(0 <= r["score"] <= 1 for r in rows[name]))
            self.assertEqual(rows[name], sorted(rows[name], key=lambda r: (-r["score"],r["model_id"])))
        self.assertTrue(all(data["model"][int(r["model_id"][1:])]["name"].startswith("chat") for r in rows["hybrid_exact"]))

    def test_generated_loads_and_eight_queries_do_not_mutate_inputs(self):
        data = corpus(30)
        original = deepcopy(data)
        pg, su = pg_load(data), surreal_load(data)
        self.assertTrue(pg.startswith("BEGIN;"))
        self.assertTrue(pg.endswith("COMMIT;"))
        self.assertIn("RELATE variant:", "\n".join(su))
        self.assertNotIn("DELETE", pg+"\n".join(su))
        self.assertNotIn("provider_ref:provider:p0", su[0])  # No self-link on provider nodes.
        self.assertEqual(set(queries()), set(expected(data)))
        self.assertEqual(data, original)

    def test_create_commands_cannot_pull_publish_or_escalate(self):
        for engine in controller.IMAGES:
            args = controller.create_arguments(engine, Path("/var/tmp/pepeuch-dbbench-test12345678"), "pepeuch-dbbench-test12345678")
            self.assertIn("--pull=never", args)
            self.assertEqual(args[args.index("--memory")+1], "4g")
            self.assertEqual(args[args.index("--cpus")+1], "2")
            self.assertEqual(args[args.index("--pids-limit")+1], "256")
            self.assertIn(controller.IMAGES[engine], args)
            for forbidden in ("--privileged", "--gpus", "--publish", "-p", "/var/run/docker.sock", "host"):
                self.assertNotIn(forbidden, args)
            self.assertFalse(any(name in " ".join(args) for name in controller.HISTORICAL))

    def test_unknown_engine_refused(self):
        with self.assertRaises(ValueError):
            controller.create_arguments("unknown", Path("/var/tmp/test"), "test")

    def test_10k_http_batches_fit_encoded_budget_without_loss_or_reordering(self):
        statements = surreal_load(corpus(10000))
        batches = list(sql_batches(statements))
        self.assertTrue(all(len(b.encode())<=512*1024 for b in batches))
        self.assertEqual([s for batch in batches for s in batch.splitlines()],statements)
        with self.assertRaises(ValueError):
            list(sql_batches(["é"*(512*1024)]))

    def test_preflight_rejects_saturation_before_any_mutation(self):
        with patch.object(controller, "inspect", side_effect=lambda kind, identity: {"Id":identity}), \
             patch.object(controller, "historical_fingerprint", return_value=[{"state":{"Status":"exited"}}]), \
             patch.object(controller.shutil, "disk_usage", return_value=type("Disk",(),{"free":100*controller.GiB})()), \
             patch.object(controller, "available_memory", return_value=controller.GiB):
            with self.assertRaises(ValueError):
                controller.preflight(Path("/var/tmp/pepeuch-dbbench-test12345678"))


def frame(kind, raw):
    return kind+struct.pack("!I", len(raw)+4)+raw


class FakeSocket:
    def __init__(self, raw):
        self.input = io.BytesIO(raw)
        self.output = bytearray()
        self.closed = False
    def recv(self, count):
        return self.input.read(min(count, 7))  # Realistic fragmented frames.
    def sendall(self, raw):
        self.output.extend(raw)
    def close(self):
        self.closed = True


class Protocol(unittest.TestCase):
    def ready(self):
        return frame(b"R", b"\0\0\0\0")+frame(b"Z", b"I")

    def test_postgres_fragmented_rows_preserve_json_null_false_zero_and_empty_list(self):
        raw = b'[{"null":null,"false":false,"zero":0,"empty":[]}]'
        row = frame(b"D",struct.pack("!Hi",1,len(raw))+raw)+frame(b"Z",b"I")
        sock = FakeSocket(self.ready()+row)
        with patch.object(clients.socket,"create_connection",return_value=sock):
            client = clients.Postgres("192.0.2.1")
            data, elapsed = client.query("SELECT 'synthetic'")
            client.close()
        self.assertEqual(data, json.loads(raw))
        self.assertGreaterEqual(elapsed, 0)
        self.assertTrue(sock.closed)

    def test_postgres_error_consumes_ready_frame_and_allows_connection_reuse(self):
        error = frame(b"E",b"C22012\0Mdivision by zero\0\0")+frame(b"Z",b"I")
        sock = FakeSocket(self.ready()+error+frame(b"Z",b"I"))
        with patch.object(clients.socket,"create_connection",return_value=sock):
            client = clients.Postgres("192.0.2.1")
            with self.assertRaises(clients.EngineError) as caught:
                client.sql("SELECT 1/0")
            self.assertEqual(caught.exception.code, "22012")
            self.assertEqual(client.sql("ROLLBACK"), [])
            client.close()

    def test_postgres_nontrust_auth_and_oversized_frames_are_refused_and_closed(self):
        for raw in (frame(b"R",struct.pack("!I",10)), b"R"+struct.pack("!I",clients.MAX_RESPONSE+5)):
            sock = FakeSocket(raw)
            with patch.object(clients.socket,"create_connection",return_value=sock), self.assertRaises(clients.EngineError):
                clients.Postgres("192.0.2.1")
            self.assertTrue(sock.closed)

    def test_surreal_error_does_not_expose_authentication_header(self):
        password = secrets.token_urlsafe(32)
        class Response:
            status = 401
            def read(self, count):
                return b'synthetic-private-body'
        with patch.object(clients.http.client,"HTTPConnection") as connection:
            connection.return_value.getresponse.return_value = Response()
            client = clients.Surreal("192.0.2.2", namespace="test", database="test", password=password)
            with self.assertRaises(clients.EngineError) as caught:
                client.query("SELECT * FROM test")
            self.assertNotIn(password, str(caught.exception))
            self.assertNotIn("synthetic-private-body", str(caught.exception))
            self.assertEqual(caught.exception.code,"surreal_http_401")

    def test_stopping_attempts_both_owned_ids_even_when_first_stop_fails(self):
        objects = {"containers":{"postgresql":"a"*64,"surrealdb":"b"*64}}
        calls=[]
        def action(*args, **kwargs):
            calls.append(args)
            if args[-1]=="a"*64:
                raise RuntimeError("simulated failure")
        with patch.object(controller,"owned_metadata",side_effect=lambda o,e:{"Id":o["containers"][e],"State":{"Running":True}}), \
             patch.object(controller,"docker",side_effect=action), patch.object(controller,"event"):
            with self.assertRaises(RuntimeError):
                controller.stop(objects,Path("/var/tmp/test"))
        self.assertEqual([c[-1] for c in calls],["a"*64,"b"*64])

    def test_surreal_plan_object_and_server_time_are_preserved_without_row_coercion(self):
        class Response:
            status = 200
            def read(self, count):
                return b'[{"status":"OK","time":"240us","result":{"plan":"synthetic-plan"}}]'
        with patch.object(clients.http.client,"HTTPConnection") as connection:
            connection.return_value.getresponse.return_value = Response()
            client = clients.Surreal("192.0.2.2", namespace="test", database="test", password=secrets.token_urlsafe(32))
            response, elapsed = client.sql("SELECT * FROM model EXPLAIN FULL;")
            self.assertEqual(response[0]["result"], {"plan":"synthetic-plan"})
            self.assertEqual(client.last_server_times,["240us"])
            self.assertGreaterEqual(elapsed,0)

    def test_surreal_large_sql_body_is_refused_before_any_network_request(self):
        with patch.object(clients.http.client,"HTTPConnection") as connection:
            client = clients.Surreal("192.0.2.2",namespace="test",database="test",password=secrets.token_urlsafe(32))
            with self.assertRaises(clients.EngineError) as caught:
                client.sql("é"*(1024*1024))
            self.assertEqual(caught.exception.code,"surreal_request_limit")
            connection.return_value.request.assert_not_called()

    def test_surreal_signin_once_uses_bearer_on_subsequent_queries_without_recording_token(self):
        password=secrets.token_urlsafe(32)
        token=secrets.token_urlsafe(64)
        class Response:
            status=200
            def __init__(self,body):self.body=body
            def read(self,count):return self.body
        with patch.object(clients.http.client,"HTTPConnection") as connection:
            connection.return_value.getresponse.side_effect=[Response(json.dumps({"code":200,"token":token}).encode()),Response(b'[{"status":"OK","time":"1ms","result":[]}]')]
            client=clients.Surreal("192.0.2.2",namespace="test",database="test",password=password,session=True)
            self.assertEqual(client.auth_mode,"bearer_session")
            client.query("SELECT * FROM model")
            calls=connection.return_value.request.call_args_list
            self.assertEqual(calls[0].args[:2],("POST","/signin"))
            self.assertEqual(calls[1].kwargs["headers"]["Authorization"],"Bearer "+token)
            self.assertNotIn(password,calls[1].kwargs["headers"]["Authorization"])
            self.assertNotIn(token,str(client.last_server_times))

    def test_surreal_invalid_signin_is_redacted_without_basic_fallback(self):
        password=secrets.token_urlsafe(32)
        class Response:
            status=403
            def read(self,count):return password.encode()
        with patch.object(clients.http.client,"HTTPConnection") as connection:
            connection.return_value.getresponse.return_value=Response()
            with self.assertRaises(clients.EngineError) as caught:
                clients.Surreal("192.0.2.2",namespace="test",database="test",password=password,session=True)
            self.assertNotIn(password,str(caught.exception))
            self.assertEqual(connection.return_value.request.call_count,1)
            connection.return_value.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
