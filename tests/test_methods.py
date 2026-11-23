import sqlite3
import unittest

import numpy as np
import pandas as pd

from src.analysis import evaluate, summarize
from src.pathway import simulate
from src.research import checks, retrieve


class MethodsTest(unittest.TestCase):
    def test_lineage_groups_and_baseline(self):
        group_count = 10
        sample_count = 6
        cohort = pd.DataFrame(
            {
                "model_id": [f"fixture-{i}" for i in range(group_count * sample_count)],
                "lineage": np.repeat([f"lineage-{i}" for i in range(group_count)], sample_count),
                "expression": np.tile(np.arange(sample_count), group_count),
            }
        )
        cohort["lactate"] = 2 * cohort["expression"] + 1
        predictions, folds = evaluate(cohort, ["expression"])
        self.assertEqual(len(predictions), len(cohort))
        self.assertTrue(predictions["model_id"].is_unique)
        self.assertTrue((predictions.groupby("lineage")["fold"].nunique() == 1).all())
        self.assertTrue((predictions["lineage_median"] == predictions["training_median"]).all())
        metrics = summarize(predictions, folds)
        self.assertLess(metrics["mae"]["ridge"], metrics["mae"]["training_median"])

    def test_pathway_equilibrium_and_clearance(self):
        _, reference, steady = simulate(2, 0.5, initial=4)
        np.testing.assert_allclose(reference, 4)
        self.assertEqual(steady, 4)
        self.assertEqual(simulate(2, 0.25)[2], 8)
        with self.assertRaisesRegex(ValueError, "positive clearance"):
            simulate(2, 0)

    def test_retrieval_and_numeric_validation(self):
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE VIRTUAL TABLE sources USING fts5(id UNINDEXED, text)")
            db.execute("INSERT INTO sources VALUES ('R1', 'The lactate pool was 4.')")
            records = retrieve(db, "What was the lactate pool?")
            self.assertEqual(records[0][0], "R1")

        question = {"id": "A", "sources": ["R1"]}
        self.assertTrue(checks(question, records, "4", "R1", True)["numbers_in_cited_record"])
        self.assertFalse(checks(question, records, "7", "R1", True)["numbers_in_cited_record"])
        self.assertFalse(checks(question, records, "4", "R2", True)["valid_citation"])
        self.assertTrue(checks(question, records, "ABSTAIN", "", True)["abstained"])


if __name__ == "__main__":
    unittest.main()
