import unittest
from agentic_redteam.campaign.plan import Campaign, execution_order


class CampaignPlanTests(unittest.TestCase):
    def test_per_deployment_groups_by_mode(self):
        c = Campaign("p@1", ["s1", "s2"], 1, ["v", "p"])
        self.assertEqual(execution_order(c, "per_deployment"),
                         [("v", "s1"), ("v", "s2"), ("p", "s1"), ("p", "s2")])

    def test_per_request_interleaves(self):
        c = Campaign("p@1", ["s1", "s2"], 1, ["v", "p"])
        self.assertEqual(execution_order(c, "per_request"),
                         [("v", "s1"), ("p", "s1"), ("v", "s2"), ("p", "s2")])

    def test_no_modes_single(self):
        c = Campaign("p@1", ["s1"], 1, [])
        self.assertEqual(execution_order(c, "per_request"), [(None, "s1")])


if __name__ == "__main__":
    unittest.main()
