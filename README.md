Of course! This is a substantial and well-structured script. A good README will help users understand its power, how to use it, and what kind of inputs it expects.

Here is a comprehensive README.md file for your script.

School Timetable Scheduler

A comprehensive, command-line tool for generating valid and optimized weekly timetables for Elementary and High Schools. The scheduler is designed to handle a complex set of rules, constraints, and preferences to produce multiple distinct and valid timetables, complete with console and PDF outputs.

Key Features

Interactive CLI: Guides the user through a step-by-step process to gather all necessary information.

Dual School Modes: Tailored logic for both Elementary (subject-based, periods/week) and High School (course-based, credits).

Smart Course Suggestion: For High Schools, automatically suggests a list of core courses and option blocks to ensure senior grades have a full schedule, significantly speeding up setup.

Powerful Constraint Engine:

Teacher Availability: Define when teachers are available or unavailable (e.g., Unavailable Mon P1-P2, Only available Tuesday afternoon).

Course Placement: Restrict courses from being scheduled in specific slots (e.g., NOT P1, NOT Friday LAST).

Forced Assignment: Pin specific courses to exact day/period slots (e.g., ASSIGN Tue P4).

Cohort Clashes: Prevent courses that a single student might take from being scheduled at the same time.

Teacher-Aware Logic:

Assigns only qualified teachers to subjects.

Respects individual teacher availability.

Enforces a minimum number of weekly prep blocks for each teacher.

Intelligent Scheduling Algorithm:

Prioritizes hard constraints (ASSIGN) before placing flexible courses.

Attempts to schedule multi-period courses at the same time each day for consistency.

Applies preferences, such as placing 3-credit courses on MWF and CTS courses on T/Th.

Rigorous Validation: Each generated schedule is checked against critical rules:

Minimum annual instructional hours are met.

Teachers have their required prep time.

Designated grades (10, 11, 12) have a full schedule with no free periods.

A high percentage of requested course periods are successfully placed.

Multiple Solutions & "Best Fail" Logic: The scheduler can generate several unique, valid timetables. If no fully valid schedule can be found, it presents the "best failed attempt" that violates the fewest critical rules.

Multiple Output Formats:

Clean, grid-based timetables in the console (via tabulate).

Professional, multi-page PDF reports for each generated schedule.

Session Caching: Remembers all your inputs between sessions in a scheduler_session_cache.tmp file, so you can easily make small changes and re-run the generator without starting from scratch.

Requirements

The script requires Python 3 and two external libraries:

reportlab: For generating PDF reports.

tabulate: For nicely formatting the timetables in the console.

Install them using pip:

pip install reportlab tabulate

How to Run

Save the script as a Python file (e.g., scheduler.py).

Install the required libraries as shown above.

Run the script from your terminal:

python scheduler.py
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Bash
IGNORE_WHEN_COPYING_END

Follow the interactive prompts to enter your school's data.

The Process: How It Works

The scheduler will guide you through the following data entry steps. Thanks to session caching, you only need to enter this information once.

School Type: Choose Elementary or High School.

Operational Parameters: Provide general school information like name, start/end dates, holidays, and daily bell times.

Schedule Structure: Define the scheduling model (Semester, Quarter, Full Year) and the daily period structure (number of periods, duration, etc.).

Define Teachers:

Enter each teacher's name.

Select their subject qualifications from a list.

Specify their availability constraints.

Define Courses / Subjects:

For High School: The script will auto-suggest a comprehensive list of core courses and option blocks. You can accept, edit, delete, or add to this list. For each course, you'll confirm its name, credits, grade level, subject area, and any scheduling constraints. The script also helps you group 1-credit courses into schedulable blocks.

For Elementary: You'll define each subject (e.g., Math, Art) and the number of periods it requires per week.

Define General Constraints (High School): Specify groups of courses that cannot be scheduled at the same time (e.g., Biology 30 and Physics 30 might clash for some students).

Generate Schedules: Tell the script how many distinct, valid schedules you want it to find.

View Results: The script will display the generated timetables in the console and ask if you want to export them to a PDF.

Input Syntax Guide

The scheduler uses a simple but flexible syntax for defining constraints.

Teacher Availability

When prompted for a teacher's availability, you can leave it blank (for "always available") or provide a string with one or more constraints separated by semicolons (;).

Example Syntax	Meaning
Unavailable Mon P1-P2	Unavailable on Monday during periods 1 and 2.
Unavailable Friday	Unavailable for the entire day on Friday.
Unavailable Mon morning	Unavailable for the first half of the periods on Monday.
Only available Tue afternoon	Only available for the second half of periods on Tuesday.
Unavailable Wed P3; Unav Fri	You can chain multiple constraints.
Course Scheduling Constraints

When defining a course, you can specify constraints on where it can be placed.

Example Syntax	Meaning
NOT P1	Cannot be scheduled in the first period of any day.
NOT Friday LAST	Cannot be scheduled in the last period on Fridays.
NOT Monday	Cannot be scheduled on Mondays.
ASSIGN Tue P4	Must be scheduled on Tuesday in period 4.
ASSIGN Mon P1; Tue P1	For multi-period courses, you can assign multiple slots.
Session Caching

The script automatically saves your inputs to a file named scheduler_session_cache.tmp in the same directory. When you re-run the script, it loads this data and presents it as the default for each prompt.

To start fresh, simply delete the scheduler_session_cache.tmp file.

To make a change, just provide a new value at the prompt when you re-run the script.

Output
Console View

A clear, grid-based timetable for each term of each generated schedule.

--- Term 1 (Sched ID: 1) ---
+-------------------+-------------------------------+-------------------------------+-------------------------------+-------------------------------+-------------------------------+
| Period/Time       | Monday                        | Tuesday                       | Wednesday                     | Thursday                      | Friday                        |
+===================+===============================+===============================+===============================+===============================+===============================+
| P1                | English 10-1                  | Science 10                    | English 10-1                  | Science 10                    | English 10-1                  |
| 08:30-09:30       | (Ms. Davis)                   | (Mr. Singh)                   | (Ms. Davis)                   | (Mr. Singh)                   | (Ms. Davis)                   |
+-------------------+-------------------------------+-------------------------------+-------------------------------+-------------------------------+-------------------------------+
| P2                | Math 10C                      | PE 10                         | Math 10C                      | PE 10                         | Math 10C                      |
| 09:35-10:35       | (Mr. Smith)                   | (Mrs. Jones)                  | (Mr. Smith)                   | (Mrs. Jones)                  | (Mr. Smith)                   |
+-------------------+-------------------------------+-------------------------------+-------------------------------+-------------------------------+-------------------------------+
...
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
IGNORE_WHEN_COPYING_END
PDF Export

A professional, landscape-oriented PDF file containing all generated schedules, with each term laid out clearly in a table. The file will be named based on the school name and date (e.g., My_School_Schedules_2023-10-27.pdf).
