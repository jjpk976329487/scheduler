# School Timetable Scheduler (WORK IN PROGRESS)

A comprehensive, command-line tool for generating valid and optimized weekly timetables for Elementary and High Schools. The scheduler is designed to handle a complex set of rules, constraints, and preferences to produce multiple distinct and valid timetables, complete with console and PDF outputs.

## Key Features

*   **Interactive CLI**: Guides the user through a step-by-step process to gather all necessary information.
*   **Dual School Modes**: Tailored logic for both Elementary (subject-based, periods/week) and High School (course-based, credits).
*   **Smart Course Suggestion**: For High Schools, automatically suggests a list of core courses and option blocks to ensure senior grades have a full schedule, significantly speeding up setup.
*   **Powerful Constraint Engine**:
    *   **Teacher Availability**: Define when teachers are available or unavailable (e.g., `Unavailable Mon P1-P2`, `Only available Tuesday afternoon`).
    *   **Course Placement**: Restrict courses from being scheduled in specific slots (e.g., `NOT P1`, `NOT Friday LAST`).
    *   **Forced Assignment**: Pin specific courses to exact day/period slots (e.g., `ASSIGN Tue P4`).
    *   **Cohort Clashes**: Prevent courses that a single student might take from being scheduled at the same time.
*   **Teacher-Aware Logic**:
    *   Assigns only qualified teachers to subjects.
    *   Respects individual teacher availability.
    *   Enforces a minimum number of weekly prep blocks for each teacher.
*   **Intelligent Scheduling Algorithm**:
    *   Prioritizes hard constraints (`ASSIGN`) before placing flexible courses.
    *   Attempts to schedule multi-period courses at the same time each day for consistency.
    *   Applies preferences, such as placing 3-credit courses on MWF and CTS courses on T/Th.
*   **Rigorous Validation**: Each generated schedule is checked against critical rules:
    *   Minimum annual instructional hours are met.
    *   Teachers have their required prep time.
    *   Designated grades (10, 11, 12) have a full schedule with no free periods.
    *   A high percentage of requested course periods are successfully placed.
*   **Multiple Solutions & "Best Fail" Logic**: The scheduler can generate several unique, valid timetables. If no fully valid schedule can be found, it presents the "best failed attempt" that violates the fewest critical rules.
*   **Multiple Output Formats**:
    *   Clean, grid-based timetables in the console (via `tabulate`).
    *   Professional, multi-page PDF reports for each generated schedule.
*   **Session Caching**: Remembers all your inputs between sessions in a `scheduler_session_cache.tmp` file, so you can easily make small changes and re-run the generator without starting from scratch.

## Requirements

The script requires Python 3 and two external libraries:

*   `reportlab`: For generating PDF reports.
*   `tabulate`: For nicely formatting the timetables in the console.

Install them using pip:
```sh
pip install reportlab tabulate
