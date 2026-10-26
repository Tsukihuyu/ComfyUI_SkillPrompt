"""Structural checks for the shipped example workflow (no ComfyUI required)."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))  # the node package is imported by folder name

import ComfyUI_SkillPrompt as pkg  # noqa: E402

WORKFLOW = ROOT / "example_workflows" / "skillprompt_moss_basic.json"


class TestExampleWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
        cls.nodes = {n["id"]: n for n in cls.wf["nodes"]}
        cls.links = {l[0]: l for l in cls.wf["links"]}

    def test_unique_ids(self):
        self.assertEqual(len(self.nodes), len(self.wf["nodes"]))
        self.assertEqual(len(self.links), len(self.wf["links"]))

    def test_last_ids_are_max(self):
        self.assertGreaterEqual(self.wf["last_node_id"], max(self.nodes))
        self.assertGreaterEqual(self.wf["last_link_id"], max(self.links))

    def test_every_link_is_wired_both_ends(self):
        for lid, (_, src, src_slot, dst, dst_slot, ltype) in self.links.items():
            self.assertIn(src, self.nodes, f"link {lid}: origin node missing")
            self.assertIn(dst, self.nodes, f"link {lid}: target node missing")

            out = self.nodes[src]["outputs"][src_slot]
            self.assertEqual(out["type"], ltype, f"link {lid}: output type mismatch")
            self.assertIn(lid, out.get("links") or [], f"link {lid}: origin does not list it")

            inp = self.nodes[dst]["inputs"][dst_slot]
            self.assertEqual(inp["type"], ltype, f"link {lid}: input type mismatch")
            self.assertEqual(inp["link"], lid, f"link {lid}: target input mismatch")

    def test_declared_links_exist(self):
        for node in self.wf["nodes"]:
            for out in node.get("outputs", []):
                for lid in out.get("links") or []:
                    self.assertIn(lid, self.links, f"node {node['id']} references missing link {lid}")
            for inp in node.get("inputs", []):
                if inp.get("link") is not None:
                    self.assertIn(inp["link"], self.links, f"node {node['id']} references missing link {inp['link']}")

    def test_our_node_widget_counts(self):
        for node in self.wf["nodes"]:
            cls = pkg.NODE_CLASS_MAPPINGS.get(node["type"])
            if not cls:
                continue
            required = list(cls.INPUT_TYPES()["required"].keys())
            self.assertEqual(
                len(node["widgets_values"]),
                len(required),
                f"{node['type']}: widgets_values {len(node['widgets_values'])} != {len(required)} inputs",
            )

    def test_our_node_widget_values_are_valid(self):
        node = next(n for n in self.wf["nodes"] if n["type"] == "SkillPromptOptimizer")
        spec = pkg.NODE_CLASS_MAPPINGS["SkillPromptOptimizer"].INPUT_TYPES()["required"]
        names = list(spec.keys())
        values = dict(zip(names, node["widgets_values"]))
        self.assertIn(values["skill"], spec["skill"][0])
        self.assertIn(values["llm_model"], spec["llm_model"][0])
        self.assertIn(values["output_format"], spec["output_format"][0])
        self.assertIn(values["language"], spec["language"][0])
        # endpoints live in skillprompt.ini, never as widgets
        self.assertNotIn("base_url", values)
        self.assertNotIn("api_key", values)

    def test_no_orphan_outputs(self):
        """Core nodes: every output must be consumed. Our nodes may leave the
        auxiliary outputs (size_note / width / height) unwired on purpose."""
        terminal = {"SaveImage", "PreviewImage"}
        for node in self.wf["nodes"]:
            if node["type"] in terminal:
                continue
            outputs = node.get("outputs", [])
            if not outputs:
                continue
            if node["type"] in pkg.NODE_CLASS_MAPPINGS:
                self.assertTrue(outputs[0].get("links"), f"node {node['id']} primary output is unwired")
                continue
            for out in outputs:
                self.assertTrue(out.get("links"), f"node {node['id']} {out['name']} is unwired")


if __name__ == "__main__":
    unittest.main(verbosity=2)
