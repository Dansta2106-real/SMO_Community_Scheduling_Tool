# output.py

import pandas as pd

from scoring import (
    calculate_score,
    print_score
)



def format_runner(
    name,
    prerecorded
):

    if prerecorded:

        return (
            f"{name} (Prerecorded)"
        )

    return name



def build_dataframe(
    solution,
    match_data,
    all_slots,
    display_time
):

    rows = []


    for race in solution["data"]:

        match = match_data[
            race["race"]
        ]


        runner1 = format_runner(
            match["runner1"],
            race["p1_prerec"]
        )


        runner2 = format_runner(
            match["runner2"],
            race["p2_prerec"]
        )


        rows.append(
            {
                "runner1":
                    runner1,

                "runner2":
                    runner2,

                "slot":
                    race["slot"],

                "scheduled":
                    display_time(
                        all_slots[
                            race["slot"]
                        ]
                    ),
            }
        )



    df = pd.DataFrame(
        rows
    )


    df = df.sort_values(
        by="slot"
    )


    return df[
        [
            "runner1",
            "runner2",
            "scheduled"
        ]
    ]



def display_solutions(
    solutions,
    match_data,
    all_slots,
    display_time,
    slots_per_day,
    output_file,
    runner_preferred_slots
):


    best_schedule = None



    for index, solution in enumerate(
        solutions[:3],
        start=1
    ):


        print()

        print(
            "=" * 15,
            f"Solution #{index}",
            "=" * 15
        )



        df = build_dataframe(
            solution,
            match_data,
            all_slots,
            display_time
        )


        print(
            df.to_string(
                index=False
            )
        )



        score = calculate_score(
            solution,
            match_data,
            runner_preferred_slots,
            len(all_slots),
            slots_per_day
        )


        print_score(
            score
        )



        if index == 1:

            best_schedule = df



    best_schedule.to_csv(
        output_file,
        index=False
    )


    print()

    print(
        f"Saved schedule to {output_file}"
    )


    return best_schedule