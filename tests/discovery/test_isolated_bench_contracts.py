"""Observed 3.3.4 plan regression + offline transactional batch protocol guards."""

from copy import deepcopy
import json
from pathlib import Path

from tests.discovery import POC_ROOT
import unittest
from unittest.mock import patch

from confirmed_sql_batches import DeliveryInterrupted, deliver, plan
from isolated_bench_ingestion import transaction
from isolated_bench_plans import duration_ms, postgres_plan, surreal_plan
from isolated_bench_workload import corpus, pg_statements, surreal_load


class Offline(unittest.TestCase):
    def setUp(self):
        for target in ("socket.create_connection", "socket.socket.connect", "socket.getaddrinfo", "subprocess.Popen"):
            guard = patch(target, side_effect=AssertionError("No real engine/network in unit contracts"))
            guard.start()
            self.addCleanup(guard.stop)


class Plans(Offline):
    def setUp(self):
        super().setUp()
        data = json.loads((POC_ROOT/"fixtures/surreal_explain_334.observed_sanitized.json").read_text())
        self.assertEqual(data["origin"],"observed_engine_response_on_synthetic_data")
        self.responses = data["responses"]

    def test_observed_filter_and_vector_trees_are_validated_without_legacy_coercion(self):
        for name, count in (("filter",4),("vector",10)):
            response = self.responses[name]
            parsed = surreal_plan(response,expected_rows=count)
            self.assertTrue(parsed["validated"])
            self.assertIsInstance(parsed["response"][0]["result"],dict)
            self.assertEqual(parsed["total_rows"],count)
            self.assertGreaterEqual(parsed["operator_count"],4)
        self.assertEqual(surreal_plan(self.responses["filter"],expected_rows=4)["root_operator_elapsed_ns"],4452)

    def test_query_duration_is_distinct_from_operator_elapsed_and_not_summed(self):
        value = surreal_plan(self.responses["filter"],expected_rows=4)
        self.assertAlmostEqual(value["envelope_server_time_ms"],.580361)
        self.assertEqual(value["root_operator_elapsed_ns"],4452)
        self.assertFalse(value["operator_times_aggregated"])
        self.assertEqual(value["scope"],"separate_profiled_execution")
        self.assertNotIn("samples_ms",value)

    def test_missing_or_unexecuted_metrics_fail_instead_of_disabling_plan_validation(self):
        for change in ("root_metrics","child_metrics","bool_counter","negative_counter","wrong_rows","legacy_array"):
            value = deepcopy(self.responses["filter"])
            root = value[0]["result"]
            if change=="root_metrics":root.pop("metrics")
            elif change=="child_metrics":root["children"][0].pop("metrics")
            elif change=="bool_counter":root["metrics"]["output_rows"]=False
            elif change=="negative_counter":root["metrics"]["elapsed_ns"]=-1
            elif change=="wrong_rows":root["total_rows"]=5
            else:value[0]["result"]=[root]
            with self.assertRaises(ValueError):surreal_plan(value,expected_rows=4)

    def test_invalid_envelope_duration_and_children_rejected(self):
        for change in ({"status":"ERR"},{"time":"not-a-duration"},{"result":None}):
            value = deepcopy(self.responses["filter"])
            value[0].update(change)
            with self.assertRaises(ValueError):surreal_plan(value,expected_rows=4)
        value = deepcopy(self.responses["filter"])
        value[0]["result"]["children"]={}
        with self.assertRaises(ValueError):surreal_plan(value,expected_rows=4)

    def test_plan_parser_owns_copy_and_retains_unknown_fields(self):
        value = deepcopy(self.responses["filter"])
        value[0]["result"]["future_unknown"]={"null":None,"false":False,"zero":0,"empty":[]}
        original = deepcopy(value)
        parsed = surreal_plan(value,expected_rows=4)
        self.assertEqual(parsed["response"],original)
        parsed["response"][0]["result"]["metrics"]["elapsed_ns"]=1
        self.assertEqual(value,original)

    def test_postgres_plan_requires_actual_execution_metrics(self):
        value=[{"Planning Time":.1,"Execution Time":.2,"Plan":{"Node Type":"Seq Scan","Actual Total Time":.2,"Actual Rows":4}}]
        parsed=postgres_plan(value,expected_rows=4)
        self.assertEqual(parsed["execution_time_ms"],.2)
        self.assertEqual(parsed["scope"],"separate_profiled_execution")
        value[0]["Plan"].pop("Actual Total Time")
        with self.assertRaises(ValueError):postgres_plan(value,expected_rows=4)


class Batches(Offline):
    def test_utf8_and_whole_multiline_statements_are_preserved(self):
        statements=["SELECT 'é;ç';", "SELECT\n '漢字';", "SELECT 3;"]
        batches=plan(statements,max_statements=1)
        self.assertEqual([b.sql for b in batches],statements)
        self.assertEqual([b.body_bytes for b in batches],[len(s.encode('utf-8')) for s in statements])
        self.assertGreater(batches[0].body_bytes,len(statements[0]))

    def test_wrapped_10k_transactions_fit_real_utf8_http_budget(self):
        data=corpus(10000)
        for engine,statements in (("postgresql",pg_statements(data)),("surrealdb",surreal_load(data))):
            batches=plan(statements)
            self.assertGreater(len(batches),1)
            self.assertTrue(all(len(transaction(engine,b).encode())<=512*1024 for b in batches))
            self.assertEqual(sum(b.sql.count(';') for b in batches),len(statements))

    def test_between_batch_interruption_reconnect_resume_and_complete_replay(self):
        batches=plan(["SELECT 1;","SELECT 2;","SELECT 3;"],max_statements=1)
        committed=[]
        calls=[]
        def send(batch):
            calls.append(batch.seq_no)
            committed.append(batch.receipt())
        def confirm(batch):return committed[-1]
        with self.assertRaises(DeliveryInterrupted):
            deliver(batches,existing=[],send=send,confirm=confirm,interrupt_after=1)
        self.assertEqual(calls,[0])
        resumed=deliver(batches,existing=deepcopy(committed),send=send,confirm=confirm)
        self.assertEqual(resumed["already_acknowledged"],1)
        self.assertEqual(calls,[0,1,2])
        replay=deliver(batches,existing=deepcopy(committed),send=send,confirm=confirm)
        self.assertEqual(replay["applied"],0)
        self.assertEqual(len(committed),3)

    def test_missing_ack_stops_before_next_batch(self):
        batches=plan(["SELECT 1;","SELECT 2;"],max_statements=1)
        calls=[]
        with self.assertRaises(ValueError):
            deliver(batches,existing=[],send=lambda b:calls.append(b.seq_no),confirm=lambda b:None)
        self.assertEqual(calls,[0])

    def test_failed_statement_stops_without_next_batch_or_ack(self):
        batches=plan(["SELECT 1;","SELECT 2;"],max_statements=1)
        calls=[]
        def fail(batch):
            calls.append(batch.seq_no)
            raise RuntimeError("synthetic-engine-failure")
        with self.assertRaises(RuntimeError):
            deliver(batches,existing=[],send=fail,confirm=lambda b:self.fail('must not acknowledge'))
        self.assertEqual(calls,[0])

    def test_wrong_manifest_gap_or_boolean_counter_cannot_be_resumed(self):
        batches=plan(["SELECT 1;","SELECT 2;"],max_statements=1)
        changed=batches[0].receipt(); changed["payload_sha256"]='0'*64
        boolean=batches[0].receipt(); boolean["seq_no"]=False
        for existing in ([changed],[batches[1].receipt()],[boolean]):
            with self.assertRaises(ValueError):
                deliver(batches,existing=existing,send=lambda b:self.fail('must not execute'),confirm=lambda b:None)

    def test_interruption_after_last_batch_is_not_misreported_as_between_batches(self):
        batches=plan(["SELECT 1;"],max_statements=1)
        with self.assertRaises(ValueError):
            deliver(batches,existing=[],send=lambda b:self.fail('must not execute'),confirm=lambda b:None,interrupt_after=1)


if __name__=='__main__':
    unittest.main()
