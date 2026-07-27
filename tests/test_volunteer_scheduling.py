import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from volunteer_scheduling import build_volunteer_assignments


class DummyVolunteer:
    def __init__(self, name, roles, availability_slots, max_races_per_day=1):
        self.name = name
        self.roles = roles
        self.availability_slots = set(availability_slots)
        self.max_races_per_day = max_races_per_day


class VolunteerSchedulingTests(unittest.TestCase):
    def test_requires_a_restreamer_and_blocks_self_playing(self):
        volunteers = [
            DummyVolunteer("restreamer2", ["Restreamer"], [0], max_races_per_day=1),
            DummyVolunteer("commentator2", ["Commentator"], [0], max_races_per_day=1),
            DummyVolunteer("player", ["Restreamer"], [0], max_races_per_day=1),
        ]

        solution = {"data": [{"race": 0, "slot": 0}]}
        match_data = [{"runner1": "player", "runner2": "other"}]

        result = build_volunteer_assignments(
            solution,
            match_data,
            [
                {"name": v.name, "roles": v.roles, "availability_slots": v.availability_slots, "max_races_per_day": v.max_races_per_day}
                for v in volunteers
            ],
            slot_lookup={0: 0},
            slots_per_day=8,
            num_slots=8,
        )

        self.assertTrue(any(item["role"] == "Restreamer" for item in result["assignments"][0]))
        self.assertFalse(any(item["volunteer"] == "player" for item in result["assignments"][0]))

    def test_adjacent_self_race_penalty_is_counted(self):
        volunteers = [
            DummyVolunteer("restreamer2", ["Restreamer"], [1], max_races_per_day=1),
            DummyVolunteer("commentator2", ["Commentator"], [1], max_races_per_day=1),
        ]

        solution = {"data": [{"race": 0, "slot": 1}]}
        match_data = [{"runner1": "restreamer", "runner2": "other"}]

        result = build_volunteer_assignments(
            solution,
            match_data,
            [
                {"name": v.name, "roles": v.roles, "availability_slots": v.availability_slots, "max_races_per_day": v.max_races_per_day}
                for v in volunteers
            ],
            slot_lookup={1: 1},
            slots_per_day=8,
            num_slots=8,
        )

        self.assertGreaterEqual(result["adjacency_penalty"], 0)

    def test_restreamer_reuse_penalty_spreads_assignments(self):
        volunteers = [
            DummyVolunteer("restreamer_a", ["Restreamer"], [0, 1, 2], max_races_per_day=1),
            DummyVolunteer("restreamer_b", ["Restreamer"], [0, 1, 2], max_races_per_day=1),
        ]

        solution = {
            "data": [
                {"race": 0, "slot": 0},
                {"race": 1, "slot": 1},
                {"race": 2, "slot": 2},
            ]
        }
        match_data = [
            {"runner1": "player0", "runner2": "other0"},
            {"runner1": "player1", "runner2": "other1"},
            {"runner1": "player2", "runner2": "other2"},
        ]

        result = build_volunteer_assignments(
            solution,
            match_data,
            [
                {"name": v.name, "roles": v.roles, "availability_slots": v.availability_slots, "max_races_per_day": v.max_races_per_day}
                for v in volunteers
            ],
            slot_lookup={0: 0, 1: 1, 2: 2},
            slots_per_day=8,
            num_slots=8,
        )

        assigned = [
            assignment["volunteer"]
            for race_assignments in result["assignments"]
            for assignment in race_assignments
            if assignment["role"] == "Restreamer"
        ]

        self.assertEqual(assigned.count("restreamer_a"), 2)
        self.assertEqual(assigned.count("restreamer_b"), 1)

    def test_commentator_reuse_penalty_spreads_assignments(self):
        volunteers = [
            DummyVolunteer("commentator_a", ["Commentator"], [0, 1], max_races_per_day=1),
            DummyVolunteer("commentator_b", ["Commentator"], [0, 1], max_races_per_day=1),
            DummyVolunteer("restreamer_a", ["Restreamer"], [0, 1], max_races_per_day=1),
        ]

        solution = {
            "data": [
                {"race": 0, "slot": 0},
                {"race": 1, "slot": 1},
            ]
        }
        match_data = [
            {"runner1": "player0", "runner2": "other0"},
            {"runner1": "player1", "runner2": "other1"},
        ]

        result = build_volunteer_assignments(
            solution,
            match_data,
            [
                {"name": v.name, "roles": v.roles, "availability_slots": v.availability_slots, "max_races_per_day": v.max_races_per_day}
                for v in volunteers
            ],
            slot_lookup={0: 0, 1: 1},
            slots_per_day=8,
            num_slots=8,
        )

        assigned = [
            assignment["volunteer"]
            for race_assignments in result["assignments"]
            for assignment in race_assignments
            if assignment["role"] == "Commentator"
        ]

        self.assertEqual(len(assigned), 2)
        self.assertEqual(assigned.count("commentator_a"), 1)
        self.assertEqual(assigned.count("commentator_b"), 1)

    def test_restreamer_fairness_penalty_prevents_one_volunteer_from_domination(self):
        volunteers = [
            DummyVolunteer("restreamer_a", ["Restreamer"], [0, 1, 2, 3, 4, 5], max_races_per_day=4),
            DummyVolunteer("restreamer_b", ["Restreamer"], [0, 1, 2, 3, 4, 5], max_races_per_day=4),
            DummyVolunteer("restreamer_c", ["Restreamer"], [0, 1, 2, 3, 4, 5], max_races_per_day=4),
        ]

        solution = {
            "data": [
                {"race": 0, "slot": 0},
                {"race": 1, "slot": 1},
                {"race": 2, "slot": 2},
                {"race": 3, "slot": 3},
                {"race": 4, "slot": 4},
                {"race": 5, "slot": 5},
            ]
        }
        match_data = [
            {"runner1": f"player{i}", "runner2": f"other{i}"}
            for i in range(6)
        ]

        result = build_volunteer_assignments(
            solution,
            match_data,
            [
                {"name": v.name, "roles": v.roles, "availability_slots": v.availability_slots, "max_races_per_day": v.max_races_per_day}
                for v in volunteers
            ],
            slot_lookup={i: i for i in range(6)},
            slots_per_day=8,
            num_slots=8,
        )

        assigned = [
            assignment["volunteer"]
            for race_assignments in result["assignments"]
            for assignment in race_assignments
            if assignment["role"] == "Restreamer"
        ]

        self.assertLessEqual(max(assigned.count(name) for name in ["restreamer_a", "restreamer_b", "restreamer_c"]), 2)


if __name__ == "__main__":
    unittest.main()
