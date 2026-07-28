# ----------------------------------------------------
# Configuration
# ----------------------------------------------------

MATCHUPS_FILE = "matchups.csv"
AVAIL_FILE = "availabilities.csv"
OUTPUT_FILE = "schedule.csv"


DAYS = [
    "thursday",
    "friday",
    "saturday",
    "sunday"
]


UTC_SLOTS = [
    "15:00",
    "16:30",
    "18:00",
    "19:30",
    "21:00",
    "22:30",
    "24:00",
    "1:30"
]


# Penalties

DOUBLE_PREREC_PENALTY = 1_000_000

PREREC_PENALTY = 100_000

ISOLATED_RACE_PENALTY = 1_000

CONSECUTIVE_BONUS = -1_000

LATE_PREREC_PENALTY = 30

# Keep fully unavailable matchups as late as possible,
# but never strong enough to justify creating new prerecords.
NO_AVAILABILITY_LATE_PENALTY = 1_000

PREFERRED_SLOT_PENALTY = 1

EMPTY_DAY_PENALTY = 1


# Number of solutions to show

TOP_SOLUTIONS = 3