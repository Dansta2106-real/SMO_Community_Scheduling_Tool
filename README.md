# Scheduling Tool

This project schedules race matchups based on runner availability and preferred slots.

## Features

- Loads runner availability data from CSV files
- Builds a scheduling model for race slots
- Writes the resulting schedule to schedule.csv

## Requirements

Install dependencies with:

```bash
pip install -r requirements.txt
```

## Usage

Run the scheduling workflow:

```bash
python scheduling_tool.py
```

Run the regression tests:

```bash
python -m unittest discover -s tests -v
```
