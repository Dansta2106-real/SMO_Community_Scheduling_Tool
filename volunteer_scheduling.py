import ast
import re

import pandas as pd
from ortools.sat.python import cp_model

from parser import DAYS, parse_time


RESTREAMER_REQUIRED_PENALTY = 10_000
COMMENTATOR_MISSING_PENALTY = 2_000
COMMENTATOR_SINGLE_PENALTY = 300
COMMENTATOR_DOUBLE_BONUS = -500
OVERFLOW_PENALTY = 20_000
ADJACENCY_PENALTY = 5_000
RESTREAMER_BACK_TO_BACK_PENALTY = 1_000
RESTREAMER_REUSE_PENALTY = 3_000
COMMENTATOR_REUSE_PENALTY = 3_000


def parse_roles(value):
    if value is None or pd.isna(value):
        return []

    text = str(value).strip()

    if not text:
        return []

    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except (SyntaxError, ValueError):
            pass

    pieces = re.split(r"\s*,\s*|\s*/\s*", text)

    roles = []

    for piece in pieces:
        role = piece.strip()
        if not role:
            continue
        if role.lower() == "commentator":
            roles.append("Commentator")
        elif role.lower() == "restreamer":
            roles.append("Restreamer")
        elif role.lower() in {"commentator/restreamer", "commentator, restreamer"}:
            roles.extend(["Commentator", "Restreamer"])
        else:
            roles.append(role)

    return roles


def load_volunteers(filename):
    volunteers = pd.read_csv(filename)
    volunteers.columns = volunteers.columns.str.strip().str.lower()

    volunteers["runner"] = (
        volunteers["runner"]
        .astype(str)
        .str.replace('"', '', regex=False)
        .str.replace("\xa0", " ", regex=False)
        .str.strip()
    )

    rows = []

    for _, row in volunteers.iterrows():
        name = row["runner"]
        roles = parse_roles(row.get("role", ""))

        availability = set()

        for day_index, day in enumerate(DAYS):
            values = row.get(day, "")

            if pd.isna(values):
                continue

            values = str(values).strip()

            if values in {"", "Nothing", "nothing"}:
                continue

            for slot in values.split(","):
                slot = slot.strip()
                if not slot or slot.lower() == "nothing":
                    continue
                try:
                    availability.add(parse_time(day_index, slot))
                except ValueError:
                    continue

        max_races = 1
        raw_max = row.get("max_races_per_day", 1)
        if pd.notna(raw_max):
            try:
                max_races = int(raw_max)
            except (TypeError, ValueError):
                max_races = 1

        rows.append(
            {
                "name": name,
                "roles": roles,
                "availability_slots": availability,
                "max_races_per_day": max_races,
            }
        )

    return rows


def _volunteer_day_key(slot_index, slots_per_day):
    return slot_index // slots_per_day


def _slot_is_adjacent(left_slot, right_slot, slots_per_day):
    if left_slot < 0 or right_slot < 0:
        return False

    same_day = left_slot // slots_per_day == right_slot // slots_per_day
    return same_day and right_slot % slots_per_day == left_slot % slots_per_day + 1


def build_volunteer_assignments(
    solution,
    match_data,
    volunteers,
    slot_lookup=None,
    slots_per_day=8,
    num_slots=None,
    all_slots=None,
):
    race_slots = [race["slot"] for race in solution["data"]]

    if num_slots is None:
        num_slots = max(race_slots, default=0) + 1

    if all_slots is None:
        all_slots = list(range(num_slots))

    race_player_names = []
    for race in solution["data"]:
        match = match_data[race["race"]]
        race_player_names.append({match["runner1"], match["runner2"]})

    model = cp_model.CpModel()
    volunteer_vars = []
    restreamer_vars = []
    commentator_vars = []
    role_lookup = []
    overflow_vars = {}
    objective_terms = []
    restreamer_assignment_vars_by_volunteer = {}
    commentator_assignment_vars_by_volunteer = {}

    for race_idx, race_slot in enumerate(race_slots):
        race_players = race_player_names[race_idx]
        day = _volunteer_day_key(race_slot, slots_per_day)
        race_role_vars = []

        for volunteer_idx, volunteer in enumerate(volunteers):
            volunteer_name = volunteer["name"]
            if volunteer_name in race_players:
                continue

            if volunteer["availability_slots"] and race_slot not in volunteer["availability_slots"]:
                continue

            role_vars = []
            if "Restreamer" in volunteer["roles"]:
                restreamer_var = model.NewBoolVar(
                    f"race_{race_idx}_volunteer_{volunteer_idx}_restreamer"
                )
                role_vars.append(restreamer_var)
                restreamer_vars.append(restreamer_var)
            if "Commentator" in volunteer["roles"]:
                commentator_var = model.NewBoolVar(
                    f"race_{race_idx}_volunteer_{volunteer_idx}_commentator"
                )
                role_vars.append(commentator_var)
                commentator_vars.append(commentator_var)

            if not role_vars:
                continue

            if len(role_vars) == 2:
                model.Add(role_vars[0] + role_vars[1] <= 1)
                assign_var = role_vars[0] + role_vars[1]
            else:
                assign_var = role_vars[0]

            reuse_var = None
            if "Restreamer" in volunteer["roles"]:
                restreamer_assignment_vars_by_volunteer.setdefault(volunteer_idx, []).append(role_vars[0])
            if "Commentator" in volunteer["roles"]:
                commentator_assignment_vars_by_volunteer.setdefault(volunteer_idx, []).append(role_vars[-1])

            volunteer_vars.append(assign_var)
            role_lookup.append((race_idx, volunteer_idx, role_vars, assign_var, reuse_var))
            race_role_vars.append(assign_var)

            for other_race_idx, other_slot in enumerate(race_slots):
                if other_race_idx == race_idx:
                    continue
                if not _slot_is_adjacent(race_slot, other_slot, slots_per_day):
                    continue
                if volunteer_name in race_player_names[other_race_idx]:
                    objective_terms.append(ADJACENCY_PENALTY * assign_var)

        if race_role_vars:
            model.Add(sum(race_role_vars) <= 3)
        else:
            raise ValueError(f"No feasible volunteers available for race {race_idx}")

        race_restreamer_vars = [entry[2][0] for entry in role_lookup if entry[0] == race_idx and len(entry[2]) > 1 and "Restreamer" in volunteer["roles"]]

    race_restreamer_vars_by_race = []
    race_commentator_vars_by_race = []
    for race_idx, _ in enumerate(race_slots):
        restreamers = []
        commentators = []
        for entry_race_idx, volunteer_idx, role_vars, assign_var, reuse_var in role_lookup:
            if entry_race_idx != race_idx:
                continue
            volunteer = volunteers[volunteer_idx]
            if "Restreamer" in volunteer["roles"]:
                restreamers.append(role_vars[0])
            if "Commentator" in volunteer["roles"]:
                commentators.append(role_vars[-1])
        race_restreamer_vars_by_race.append(restreamers)
        race_commentator_vars_by_race.append(commentators)

    for race_idx, user_vars in enumerate(race_restreamer_vars_by_race):
        if user_vars:
            model.Add(sum(user_vars) >= 1)
        else:
            raise ValueError(f"No restreamer volunteers available for race {race_idx}")

    for race_idx, user_vars in enumerate(race_commentator_vars_by_race):
        if user_vars:
            model.Add(sum(user_vars) <= 2)

    # Limit volunteer slots per day, allowing overflow only when needed.
    for volunteer_idx, volunteer in enumerate(volunteers):
        for day in range(4):
            day_vars = []
            for race_idx, race_slot in enumerate(race_slots):
                if _volunteer_day_key(race_slot, slots_per_day) != day:
                    continue
                for entry_race_idx, entry_volunteer_idx, role_vars, assign_var, reuse_var in role_lookup:
                    if entry_race_idx == race_idx and entry_volunteer_idx == volunteer_idx:
                        day_vars.extend(role_vars)
                        break
            if not day_vars:
                continue
            overflow_var = model.NewBoolVar(f"volunteer_{volunteer_idx}_day_{day}_overflow")
            overflow_vars[(volunteer_idx, day)] = overflow_var
            model.Add(sum(day_vars) <= volunteer["max_races_per_day"] + overflow_var)
            objective_terms.append(OVERFLOW_PENALTY * overflow_var)

    for volunteer_idx, volunteer in enumerate(volunteers):
        if "Restreamer" in volunteer["roles"]:
            restreamer_vars = restreamer_assignment_vars_by_volunteer.get(volunteer_idx, [])
            if restreamer_vars:
                overflow_var = model.NewBoolVar(f"restreamer_overflow_{volunteer_idx}")
                model.Add(sum(restreamer_vars) <= 2 + overflow_var)
                objective_terms.append(RESTREAMER_REUSE_PENALTY * overflow_var)

        if "Commentator" in volunteer["roles"]:
            commentator_vars = commentator_assignment_vars_by_volunteer.get(volunteer_idx, [])
            if commentator_vars:
                overflow_var = model.NewBoolVar(f"commentator_overflow_{volunteer_idx}")
                model.Add(sum(commentator_vars) <= 2 + overflow_var)
                objective_terms.append(COMMENTATOR_REUSE_PENALTY * overflow_var)

    # Commentator preference objective.
    for race_idx, race_commentators in enumerate(race_commentator_vars_by_race):
        if not race_commentators:
            continue
        commentator_count = sum(race_commentators)
        zero_commentators = model.NewBoolVar(f"race_{race_idx}_zero_commentators")
        one_commentator = model.NewBoolVar(f"race_{race_idx}_one_commentator")
        two_commentators = model.NewBoolVar(f"race_{race_idx}_two_commentators")

        model.Add(commentator_count == 0).OnlyEnforceIf(zero_commentators)
        model.Add(commentator_count != 0).OnlyEnforceIf(zero_commentators.Not())
        model.Add(commentator_count == 1).OnlyEnforceIf(one_commentator)
        model.Add(commentator_count != 1).OnlyEnforceIf(one_commentator.Not())
        model.Add(commentator_count == 2).OnlyEnforceIf(two_commentators)
        model.Add(commentator_count != 2).OnlyEnforceIf(two_commentators.Not())

        objective_terms.append(COMMENTATOR_MISSING_PENALTY * zero_commentators)
        objective_terms.append(COMMENTATOR_SINGLE_PENALTY * one_commentator)
        objective_terms.append(COMMENTATOR_DOUBLE_BONUS * two_commentators)

    # Prefer restreamers to be assigned to adjacent races when possible.
    for race_idx, race_slot in enumerate(race_slots):
        if race_idx >= len(race_slots) - 1:
            continue
        next_slot = race_slots[race_idx + 1]
        if not _slot_is_adjacent(race_slot, next_slot, slots_per_day):
            continue

        for entry_race_idx, volunteer_idx, role_vars, assign_var, reuse_var in role_lookup:
            if entry_race_idx != race_idx:
                continue
            volunteer = volunteers[volunteer_idx]
            if "Restreamer" not in volunteer["roles"]:
                continue
            for next_entry_race_idx, next_volunteer_idx, next_role_vars, next_assign_var, next_reuse_var in role_lookup:
                if next_entry_race_idx != race_idx + 1:
                    continue
                next_volunteer = volunteers[next_volunteer_idx]
                if "Restreamer" not in next_volunteer["roles"]:
                    continue
                if volunteer_idx == next_volunteer_idx:
                    continue
                pair_var = model.NewBoolVar(
                    f"restreamer_pair_{race_idx}_{volunteer_idx}_{next_volunteer_idx}"
                )
                model.AddBoolAnd([role_vars[0], next_role_vars[0]]).OnlyEnforceIf(pair_var)
                model.AddBoolOr([role_vars[0].Not(), next_role_vars[0].Not()]).OnlyEnforceIf(pair_var.Not())
                objective_terms.append(RESTREAMER_BACK_TO_BACK_PENALTY * pair_var)
                break
            break

    model.Minimize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 4
    solver.parameters.max_time_in_seconds = 20
    solver.parameters.random_seed = 0
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise ValueError("No feasible volunteer assignment found")

    assignments = []
    for race_idx, _ in enumerate(race_slots):
        race_assignments = []
        for entry_race_idx, volunteer_idx, role_vars, assign_var, reuse_var in role_lookup:
            if entry_race_idx != race_idx:
                continue
            volunteer = volunteers[volunteer_idx]
            if len(role_vars) == 2:
                if solver.Value(role_vars[0]):
                    role = "Restreamer"
                elif solver.Value(role_vars[1]):
                    role = "Commentator"
                else:
                    continue
            else:
                if solver.Value(role_vars[0]):
                    role = "Restreamer" if "Restreamer" in volunteer["roles"] else "Commentator"
                else:
                    continue
            race_assignments.append({"volunteer": volunteer["name"], "role": role})
        assignments.append(race_assignments)

    return {
        "assignments": assignments,
        "overflow_count": sum(1 for value in overflow_vars.values() if solver.Value(value)),
        "adjacency_penalty": sum(
            ADJACENCY_PENALTY
            for _ in range(0)
        ),
    }
