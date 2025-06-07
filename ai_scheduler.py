import datetime
import math
import random
import copy
import json
import os
import traceback # For more detailed error reporting
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from collections import defaultdict

# --- Constants ---
ELEMENTARY_MIN_HOURS = 950
HIGH_SCHOOL_MIN_HOURS = 1000
DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
CREDITS_TO_HOURS_PER_CREDIT = 25
TYPICAL_COURSE_CREDITS_FOR_ESTIMATE = 5
MAX_DISTINCT_SCHEDULES_TO_GENERATE = 1
MIN_PREP_BLOCKS_PER_WEEK = 2
GRADES_REQUIRING_FULL_SCHEDULE = [10, 11, 12]
POSSIBLE_OPTION_BLOCK_SIZES = [3, 1, 5, 2, 4]

# --- SA Constants ---
SA_INITIAL_TEMPERATURE = 1000.0
SA_COOLING_RATE = 0.99
SA_MIN_TEMPERATURE = 0.1
SA_ITERATIONS_PER_TEMPERATURE = 150
SA_MAX_TOTAL_ITERATIONS = 75000

# --- Cost Function Penalties ---
PENALTY_HARD_CONSTRAINT_VIOLATION = 1000
PENALTY_TEACHER_QUALIFICATION = 1500
PENALTY_COHORT_CLASH = 1200
PENALTY_INSUFFICIENT_PREP = 800
PENALTY_UNMET_GRADE_SLOT = 700
PENALTY_UNPLACED_COURSE_PERIOD = 500
PENALTY_TEACHER_OVERLOAD_SOFT = 50
PENALTY_COURSE_NOT_IN_PREFERRED_SLOT_TYPE = 10
PENALTY_MISSING_CREE_PER_TERM = 900
PENALTY_COURSE_PERIOD_INCONSISTENCY = 100
PENALTY_CREDIT_MINUTES_MISMATCH = 75 # NEW: Penalty for incorrect minutes per credit


QUALIFIABLE_SUBJECTS = [
    "Math", "Science", "Social Studies", "English", "French",
    "PE", "Cree", "CTS", "Other"
]

CORE_SUBJECTS_HS = ["English", "Math", "Science", "Social Studies"]

HIGH_SCHOOL_COURSE_CREDITS_TEMPLATE = {
    # Grade 10
    "English 10-1": 5, "English 10-2": 5, "English 10-4": 5,
    "Social Studies 10-1": 5, "Social Studies 10-2": 5, "Social Studies 10-4": 5,
    "Math 10C": 5, "Math 10-3": 5, "Math 10-4": 5,
    "Science 10": 5, "Science 14": 5, "Science 10-4": 5,
    "Physical Education 10": 5,
    "CALM 20": 3,
    "Art 10": 3, "Drama 10": 3, "Music 10": 3, "French 10": 5,
    "Cree 10-3Y": 5,
    "Construction Technologies 10": 5, "Fashion Studies 10": 5, "Foods 10": 5,
    "Outdoor Education 10": 3, "Environmental Stewardship 10": 3,

    # Grade 11
    "English 20-1": 5, "English 20-2": 5, "English 20-4": 5,
    "Social Studies 20-1": 5, "Social Studies 20-2": 5, "Social Studies 20-4": 5,
    "Math 20-1": 5, "Math 20-2": 5, "Math 20-3": 5, "Math 20-4": 5,
    "Biology 20": 5, "Chemistry 20": 5, "Physics 20": 5, "Science 20": 5,
    "Science 24": 5, "Science 20-4": 5,
    "Art 20": 5, "Drama 20": 5, "Music 20": 5, "French 20": 5,
    "Cree 20-3Y": 5,
    "Construction Technologies 20": 5, "Fashion Studies 20": 5, "Foods 20": 5,
    "Outdoor Education 20": 3, "Environmental Stewardship 20": 3,

    # Grade 12
    "English 30-1": 5, "English 30-2": 5, "English 30-4": 5,
    "Social Studies 30-1": 5, "Social Studies 30-2": 5,
    "Math 30-1": 5, "Math 30-2": 5, "Math 30-3": 5, "Math 30-4": 5,
    "Biology 30": 5, "Chemistry 30": 5, "Physics 30": 5, "Science 30": 5,
    "Art 30": 5, "Drama 30": 5, "Music 30": 5, "French 30": 5,
    "Cree 30-3Y": 5,
    "Construction Technologies 30": 5, "Fashion Studies 30": 5, "Foods 30": 5,
    "Outdoor Education 30": 3, "Environmental Stewardship 30": 3,
}

# --- Helper Functions ---
def parse_time(time_str):
    try: return datetime.datetime.strptime(time_str, "%I:%M %p").time()
    except ValueError:
        try: return datetime.datetime.strptime(time_str, "%H:%M").time()
        except ValueError: return None

def parse_date(date_str):
    try: return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError: return None

def time_to_minutes(time_obj):
    if not time_obj: return 0
    return time_obj.hour * 60 + time_obj.minute

def format_time_from_minutes(minutes_since_midnight):
    hours = minutes_since_midnight // 60
    minutes = minutes_since_midnight % 60
    return f"{int(hours):02d}:{int(minutes):02d}"

def calculate_instructional_days(start_date, end_date, non_instructional_days_str):
    non_instructional_dates = []
    if non_instructional_days_str:
        for ds in non_instructional_days_str.split(','):
            pd = parse_date(ds.strip())
            if pd: non_instructional_dates.append(pd)
    days = 0
    if start_date and end_date and start_date <= end_date:
        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() < 5 and current_date not in non_instructional_dates:
                days += 1
            current_date += datetime.timedelta(days=1)
    return days

def parse_teacher_availability(availability_str, num_periods):
    if not isinstance(num_periods, int) or num_periods <= 0:
        num_periods = 1

    availability = {day: {p: True for p in range(num_periods)} for day in DAYS_OF_WEEK}
    if not availability_str or availability_str.lower() == "always" or availability_str.lower() == "always available":
        return availability

    for constraint_part in availability_str.split(';'):
        constraint = constraint_part.strip()
        if not constraint: continue
        try:
            parts = constraint.split()
            if len(parts) < 2: continue
            day_short = parts[0][:3].capitalize()
            day_full = next((d for d in DAYS_OF_WEEK if d.startswith(day_short)), None)
            if not day_full: continue

            period_part_str = parts[1].upper()
            if period_part_str.startswith("P"):
                spec = period_part_str[1:]
                if '-' in spec:
                    s, e = map(int, spec.split('-'))
                    for p_idx in range(s - 1, e):
                        if 0 <= p_idx < num_periods: availability[day_full][p_idx] = False
                else:
                    p_num = int(spec) - 1
                    if 0 <= p_num < num_periods: availability[day_full][p_num] = False
            else:
                is_morn = "morning" in constraint.lower()
                is_aft = "afternoon" in constraint.lower()
                is_only = "only" in constraint.lower()
                is_unavail = "unavailable" in constraint.lower() or "not available" in constraint.lower()
                mid_p = num_periods // 2
                if is_only:
                    if is_morn:
                        for p_idx in range(mid_p, num_periods): availability[day_full][p_idx] = False
                    elif is_aft:
                        for p_idx in range(0, mid_p): availability[day_full][p_idx] = False
                elif is_unavail:
                    if is_morn:
                        for p_idx in range(0, mid_p): availability[day_full][p_idx] = False
                    if is_aft:
                        for p_idx in range(mid_p, num_periods): availability[day_full][p_idx] = False
                    if not is_morn and not is_aft:
                         for p_idx in range(num_periods): availability[day_full][p_idx] = False
        except Exception: pass
    return availability

def parse_scheduling_constraint(constraint_str, num_periods):
    parsed_constraints = []
    if not isinstance(num_periods, int) or num_periods <= 0: num_periods = 1
    constraint_str_upper = constraint_str.upper().strip()
    type_val, content = None, ""

    if constraint_str_upper.startswith("NOT "): type_val, content = "NOT", constraint_str[4:].strip()
    elif constraint_str_upper.startswith("ASSIGN "): type_val, content = "ASSIGN", constraint_str[7:].strip()
    else: return parsed_constraints

    if type_val == "ASSIGN":
        for slot_str in content.replace(',', ';').split(';'):
            slot_str = slot_str.strip()
            if not slot_str: continue
            parts = slot_str.split()
            if len(parts) == 2:
                day_short = parts[0][:3].capitalize()
                day_full = next((d for d in DAYS_OF_WEEK if d.startswith(day_short)), None)
                period_spec = parts[1].upper().replace("P", "")
                try:
                    p_idx = int(period_spec) - 1
                    if day_full and 0 <= p_idx < num_periods:
                        parsed_constraints.append({'type': 'ASSIGN', 'day': day_full, 'period': p_idx})
                except ValueError: pass
        return parsed_constraints

    target_day_not, parts_not = None, content.split()
    if parts_not:
        day_cand_upper = parts_not[0].upper()
        for day_name_iter in DAYS_OF_WEEK:
            if day_cand_upper == day_name_iter.upper() or day_cand_upper == day_name_iter[:3].upper():
                target_day_not, parts_not = day_name_iter, parts_not[1:]; break

    days_to_apply = [target_day_not] if target_day_not else DAYS_OF_WEEK
    if not parts_not:
        for day_apply in days_to_apply:
            for p_idx in range(num_periods):
                parsed_constraints.append({'type': 'NOT', 'day': day_apply, 'period': p_idx})
        return parsed_constraints

    spec_not, indices_to_constrain = parts_not[0].upper(), []
    try:
        if spec_not.startswith("P"):
            period_part_not = spec_not[1:]
            if '-' in period_part_not:
                s_p_str, e_p_str = period_part_not.split('-'); s_p, e_p = int(s_p_str)-1, int(e_p_str)-1
                indices_to_constrain.extend(range(s_p, e_p + 1))
            else: indices_to_constrain.append(int(period_part_not) - 1)
        elif spec_not == "AFTERNOON": indices_to_constrain.extend(range(num_periods // 2, num_periods))
        elif spec_not == "MORNING": indices_to_constrain.extend(range(0, num_periods // 2))
        elif spec_not == "LAST" and num_periods > 0: indices_to_constrain.append(num_periods - 1)
        elif spec_not == "FIRST" and num_periods > 0: indices_to_constrain.append(0)
    except ValueError: pass

    for day_apply_final in days_to_apply:
        for p_idx_con in indices_to_constrain:
            if 0 <= p_idx_con < num_periods:
                parsed_constraints.append({'type': 'NOT', 'day': day_apply_final, 'period': p_idx_con})
    return parsed_constraints

class SchoolScheduler:
    def __init__(self):
        self.session_cache = {}
        self.generated_schedules_details = []
        self.params = {}
        self.teachers_data = []
        self.courses_data_master = []
        self.subjects_data = []
        self.cohort_constraints = []
        self.current_run_log = []
        self.high_school_credits_db = copy.deepcopy(HIGH_SCHOOL_COURSE_CREDITS_TEMPLATE)
        self.course_details_map = {}


    def _log_message(self, message, level="INFO"):
        self.current_run_log.append(f"[{level}] {message}")

    def get_input_with_default(self, key, prompt, data_type=str, validation_func=None, allow_empty=False, choices=None, default_value_override=None):
        cached_value = None
        if default_value_override is not None:
            cached_value = default_value_override
        elif key:
            cached_value = self.session_cache.get(key)

        display_prompt = prompt
        if choices:
            choice_str = ", ".join([f"({i+1}) {choice}" for i, choice in enumerate(choices)])
            display_prompt += f" [{choice_str}]"

        if cached_value is not None:
            default_display = str(cached_value)
            if choices:
                try:
                    idx = -100
                    if isinstance(cached_value, str) and cached_value.isdigit(): idx = int(cached_value) - 1
                    elif isinstance(cached_value, int): idx = cached_value -1
                    elif isinstance(cached_value, str) and cached_value in choices: idx = choices.index(cached_value)
                    if 0 <= idx < len(choices): default_display = choices[idx]
                except (ValueError, TypeError, IndexError):
                    if isinstance(cached_value, str) and cached_value in choices: default_display = cached_value
            display_prompt += f" (default: {default_display}): "
        else: display_prompt += ": "

        while True:
            user_input_raw = input(display_prompt).strip()
            value_to_process = user_input_raw if user_input_raw or cached_value is None else str(cached_value)

            if allow_empty and not value_to_process:
                if key: self.session_cache[key] = ""
                return ""
            if not value_to_process and not allow_empty:
                 print("Input cannot be empty."); continue

            try:
                converted_value, value_to_cache = None, value_to_process
                if choices:
                    try:
                        choice_idx = int(value_to_process) - 1
                        if 0 <= choice_idx < len(choices):
                            converted_value = choices[choice_idx]
                            value_to_cache = value_to_process
                        else: print(f"Invalid choice number."); continue
                    except ValueError:
                        matched = False
                        for choice_text_iter in choices:
                            if value_to_process.lower() == choice_text_iter.lower():
                                converted_value, matched = choice_text_iter, True
                                value_to_cache = choice_text_iter
                                break
                        if not matched: print(f"Invalid choice text."); continue
                elif data_type == int: converted_value = int(value_to_process)
                elif data_type == float: converted_value = float(value_to_process)
                else: converted_value = str(value_to_process)

                if validation_func:
                    if validation_func(converted_value):
                        if key: self.session_cache[key] = value_to_cache
                        return converted_value
                    else: continue
                else:
                    if key: self.session_cache[key] = value_to_cache
                    return converted_value
            except ValueError: print(f"Invalid input type. Expected {data_type.__name__}.")

    def display_info_needed(self):
        print("\n--- Information Needed to Complete the Schedule ---")
        print("\n**General School Information:**")
        print("  - School Name, Year Start/End Dates, Non-Instructional Days")
        print("  - Daily School Start/End Times, Lunch Break Times")
        print("  - Policy: Can classes appear multiple times on the same day?")
        print("\n**Schedule Structure:**")
        print("  - Type: Quarterly, Semester, or Full Year")
        print("  - Number of teaching periods/day, Duration of periods, Duration of breaks")
        print("  - Number of concurrent class slots (tracks) per period")
        print("  - (Scheduler will prioritize scheduling multi-period courses at the same time daily if possible)")
        print("  - (Scheduler will prioritize 3-credit courses on MWF, CTS courses on T/Th where feasible)")
        print(f"  - (Scheduler will ensure Grades {', '.join(map(str, GRADES_REQUIRING_FULL_SCHEDULE))} have a class offering in every period slot)")
        print("\n**Teacher Information:**")
        print(f"  - Teacher Names, Availability/Unavailability (e.g., 'Unavailable Mon P1-P2')")
        print(f"    CRITICAL: Ensure teachers have sufficient available slots defined for teaching and prep.")
        print(f"  - Subjects each teacher is qualified to teach (from list: {', '.join(QUALIFIABLE_SUBJECTS)})")
        print(f"  - (The system will aim for at least {MIN_PREP_BLOCKS_PER_WEEK} prep blocks per teacher per week within their availability)")
        print("\n**Course/Subject Information:**")
        print("  **Elementary:** Subjects, Periods/week, Constraints (e.g., 'Math NOT P1')")
        print("  **High School:** Courses, Credits, Grade Level (10, 11, 12, or Mixed), Subject Area, Term, Constraints, Cohort Clashes")
        print("    - New: Option to enforce at least one Cree class per term.")
        print("    - New: Scheduler will penalize if weekly minutes for 1, 3, or 5 credit courses deviate from targets.")
        input("\nPress Enter to continue...")
        print("-" * 50)

    def get_school_type(self):
        print("\n--- School Type Selection ---")
        school_type_choice = self.get_input_with_default('school_type_choice', "School Type", str, lambda x: x in ['Elementary', 'High School'], choices=['Elementary', 'High School'])
        if school_type_choice == "Elementary":
            self.params['school_type'], self.params['min_instructional_hours'] = "Elementary", ELEMENTARY_MIN_HOURS
        elif school_type_choice == "High School":
            self.params['school_type'], self.params['min_instructional_hours'] = "High School", HIGH_SCHOOL_MIN_HOURS
        self.session_cache['min_instructional_hours'] = self.params.get('min_instructional_hours')
        self._log_message(f"Selected: {self.params.get('school_type')} School", "INFO")

    def get_operational_parameters(self):
        self._log_message("--- School Operational Parameters ---", "DEBUG")
        self.params['school_name'] = self.get_input_with_default('school_name', "School Name", str, lambda x: len(x) > 0)
        while True:
            start_date_str = self.get_input_with_default('start_date_str', "School Year Start Date (YYYY-MM-DD)", str)
            self.params['start_date'] = parse_date(start_date_str)
            if self.params['start_date']: self.session_cache['start_date_str'] = start_date_str; break
            else: print("Invalid date format.")
        while True:
            end_date_str = self.get_input_with_default('end_date_str', "School Year End Date (YYYY-MM-DD)", str)
            self.params['end_date'] = parse_date(end_date_str)
            if self.params['end_date'] and self.params.get('start_date') and self.params['end_date'] > self.params['start_date']:
                self.session_cache['end_date_str'] = end_date_str; break
            else: print("Invalid date format or end date not after start date.")
        self.params['non_instructional_days_str'] = self.get_input_with_default('non_instructional_days_str', "Non-instructional days (YYYY-MM-DD, comma-separated)", str, allow_empty=True)
        while True:
            start_time_str = self.get_input_with_default('start_time_str', "Daily School Start Time (HH:MM AM/PM or HH:MM)", str)
            self.params['school_start_time'] = parse_time(start_time_str)
            if self.params['school_start_time']: self.session_cache['start_time_str'] = start_time_str; break
            else: print("Invalid time format.")
        while True:
            end_time_str = self.get_input_with_default('end_time_str', "Daily School End Time (HH:MM AM/PM or HH:MM)", str)
            self.params['school_end_time'] = parse_time(end_time_str)
            if self.params['school_end_time'] and self.params.get('school_start_time') and time_to_minutes(self.params['school_end_time']) > time_to_minutes(self.params['school_start_time']):
                self.session_cache['end_time_str'] = end_time_str; break
            else: print("Invalid time format or end time not after start.")
        while True:
            lunch_start_str = self.get_input_with_default('lunch_start_time_str', "Lunch Start Time (HH:MM AM/PM or HH:MM)", str)
            self.params['lunch_start_time'] = parse_time(lunch_start_str)
            s_st, s_et = self.params.get('school_start_time'), self.params.get('school_end_time')
            if self.params['lunch_start_time'] and s_st and s_et and time_to_minutes(s_st) <= time_to_minutes(self.params['lunch_start_time']) < time_to_minutes(s_et):
                self.session_cache['lunch_start_time_str'] = lunch_start_str; break
            else: print("Invalid time or lunch outside school hours.")
        while True:
            lunch_end_str = self.get_input_with_default('lunch_end_time_str', "Lunch End Time (HH:MM AM/PM or HH:MM)", str)
            self.params['lunch_end_time'] = parse_time(lunch_end_str)
            l_st, s_et = self.params.get('lunch_start_time'), self.params.get('school_end_time')
            if self.params['lunch_end_time'] and l_st and s_et and time_to_minutes(l_st) < time_to_minutes(self.params['lunch_end_time']) <= time_to_minutes(s_et):
                self.session_cache['lunch_end_time_str'] = lunch_end_str; break
            else: print("Invalid time or lunch end not after start / outside school hours.")
        multiple_choice = self.get_input_with_default('multiple_times_same_day_choice', "Can a specific course/subject (for the same grade/cohort) appear multiple times on the same day's schedule?", str, lambda x: x.lower() in ['yes', 'no'], choices=['yes', 'no'])
        self.params['multiple_times_same_day'] = multiple_choice.lower() == 'yes'
        self.params['instructional_days'] = calculate_instructional_days(self.params.get('start_date'), self.params.get('end_date'), self.params.get('non_instructional_days_str',''))
        self.session_cache['instructional_days'] = self.params.get('instructional_days')
        num_id = self.params.get('instructional_days',0)
        self.params['num_instructional_weeks'] = math.ceil(num_id / 5) if num_id > 0 else 0
        self.session_cache['num_instructional_weeks'] = self.params.get('num_instructional_weeks')
        self._log_message(f"Calculated Instructional Days: {self.params.get('instructional_days')}, Weeks: {self.params.get('num_instructional_weeks')}", "DEBUG")

    def get_course_structure_model(self):
        self._log_message("--- Course Structure Model ---", "DEBUG")
        model_choices_map = {"Quarterly": ("Quarterly", 4), "Semester": ("Semester", 2), "Full Year": ("Full Year", 1)}
        chosen_model_text = self.get_input_with_default('course_model_choice_text', "Select scheduling model", str, lambda x: x in model_choices_map, choices=list(model_choices_map.keys()))
        self.params['scheduling_model'], self.params['num_terms'] = model_choices_map[chosen_model_text]
        num_iw, num_t = self.params.get('num_instructional_weeks',0), self.params.get('num_terms',0)
        self.params['weeks_per_term'] = math.ceil(num_iw / num_t) if num_iw > 0 and num_t > 0 else 0
        self.session_cache['weeks_per_term'] = self.params.get('weeks_per_term')
        self._log_message(f"Model: {self.params.get('scheduling_model')} ({num_t} terms), Weeks/term: {self.params.get('weeks_per_term')}", "DEBUG")

    def get_period_structure_details(self):
        self._log_message("--- Daily Period Structure ---", "DEBUG")
        self.params['num_periods_per_day'] = self.get_input_with_default('num_periods_per_day', "Number of teaching periods/day", int, lambda x: x > 0)
        self.params['period_duration_minutes'] = self.get_input_with_default('period_duration_minutes', "Duration of each period (minutes)", int, lambda x: x > 0)
        self.params['num_concurrent_tracks_per_period'] = self.get_input_with_default('num_concurrent_tracks_per_period', "Number of concurrent class slots (tracks) per period", int, lambda x: x >= 1)
        breaks_val_str = self.get_input_with_default('break_between_classes_minutes_str', "Duration of breaks between classes (minutes, default 5)", str, allow_empty=True)
        self.params['break_between_classes_minutes'] = int(breaks_val_str) if breaks_val_str else 5
        if self.params.get('break_between_classes_minutes', 5) < 0: self.params['break_between_classes_minutes'] = 0
        self.session_cache['break_between_classes_minutes'] = self.params.get('break_between_classes_minutes')

        s_st, s_et = self.params.get('school_start_time'), self.params.get('school_end_time')
        l_st, l_et = self.params.get('lunch_start_time'), self.params.get('lunch_end_time')
        available_min = 0
        if all([s_st, s_et, l_st, l_et]):
            available_min = (time_to_minutes(s_et) - time_to_minutes(s_st)) - \
                            (time_to_minutes(l_et) - time_to_minutes(l_st))

        num_p = self.params.get('num_periods_per_day',0)
        p_dur = self.params.get('period_duration_minutes',0)
        b_dur = self.params.get('break_between_classes_minutes',0)
        required_min = (num_p * p_dur) + (max(0, num_p - 1) * b_dur)

        if required_min > available_min and available_min > 0 :
            self._log_message(f"Daily schedule duration might not fit! Required: {required_min} min, Available: {available_min} min.", "WARNING")

        total_annual_hours = (self.params.get('instructional_days', 0) * num_p * p_dur) / 60
        self.params['total_annual_instructional_hours'] = total_annual_hours
        self.session_cache['total_annual_instructional_hours'] = total_annual_hours
        self._log_message(f"Total Annual Instructional Hours (per track): {total_annual_hours:.2f}.", "DEBUG")
        if total_annual_hours < self.params.get('min_instructional_hours',0):
            self._log_message(f"Hours ({total_annual_hours:.2f}) BELOW Alberta minimum ({self.params.get('min_instructional_hours',0)}).", "WARNING")

    def _get_suggested_core_courses(self):
        suggested_courses_all_grades = []
        num_terms = self.params.get('num_terms', 1)

        if self.params.get('school_type') != 'High School':
            return []

        num_p_day = self.params.get('num_periods_per_day', 1)
        p_dur_min = self.params.get('period_duration_minutes', 1)
        num_tracks = self.params.get('num_concurrent_tracks_per_period', 1)

        if not all(isinstance(val, int) and val > 0 for val in [num_p_day, p_dur_min, num_tracks]):
            self._log_message("ERROR: Invalid period structure parameters for suggestions.", "ERROR")
            return []

        # Total period-instances the school can offer per week across all tracks
        total_weekly_school_slots = num_p_day * num_tracks * len(DAYS_OF_WEEK)
        self._log_message(f"Suggest Engine: Total weekly school slots capacity = {total_weekly_school_slots}", "DEBUG")

        # Weeks a course runs (depends on model: term-based or full year)
        # This is used to calculate periods_per_week from total periods for a course.
        weeks_course_duration_for_calc = self.params.get('weeks_per_term', 18)
        if self.params.get('scheduling_model') == "Full Year":
            weeks_course_duration_for_calc = self.params.get('num_instructional_weeks', 36)
        if not isinstance(weeks_course_duration_for_calc, int) or weeks_course_duration_for_calc <= 0:
            weeks_course_duration_for_calc = 18 # Fallback

        # Keep track of available slots per term
        # Initialize with total capacity, will be reduced as courses are "suggested"
        # For suggestions, we assume each course takes one track slot.
        # The actual SA will handle multi-track placement.
        # Here, available_slots_per_term is the number of *distinct course offerings* we can suggest per week.
        available_slots_per_term_week = {term: total_weekly_school_slots for term in range(1, num_terms + 1)}


        # Define core subject streams (customize as needed, -1 is often diploma, -2 general, -4 K&E)
        # Order matters for suggestion priority if capacity is tight.
        core_streams_by_subject = {
            "English": ["-1", "-2", "-4"],
            "Math": ["C", "-1", "-2", "-3", "-4"], # Math 10C, 20-1, 30-1 etc.
            "Science": [" 10", " 14", " 10-4", " 20", " 24", " 20-4", " 30"], # Sci 10, Bio 20, Chem 30 etc.
            "Social Studies": ["-1", "-2", "-4"]
        }
        # Base names for easier matching
        base_core_subjects = {
            "English": "English", "Math": "Math", "Science": "Science", "Social Studies": "Social Studies"
        }
        other_important_courses = { # (Course Name, Subject Area, Default Term Preference)
            10: [("CALM 20", "Other", 1), ("Physical Education 10", "PE", None), ("Cree 10-3Y", "Cree", 1)],
            11: [("Cree 20-3Y", "Cree", 1)],
            12: [("Cree 30-3Y", "Cree", 1)],
        }
        grades_to_schedule = [10, 11, 12] # Order of grade priority for core suggestions

        # --- Pass 1: Suggest one primary stream of each core for each grade, plus other important ---
        self._log_message("Suggest Engine: Pass 1 - Primary Cores & Important Electives", "INFO")
        suggested_this_pass = [] # Temp list for this pass

        for term_num_suggest in range(1, num_terms + 1):
            self._log_message(f"Suggest Engine: Pass 1 - Considering Term {term_num_suggest}", "DEBUG")
            for grade in grades_to_schedule:
                # Suggest one stream of each core subject
                for subj_cat, base_name in base_core_subjects.items():
                    stream_found_for_subj = False
                    for stream_suffix in core_streams_by_subject[subj_cat]:
                        course_name_candidate = f"{base_name} {grade//10}0{stream_suffix}" # e.g. English 10-1, Math 20-2
                        if subj_cat == "Math" and stream_suffix == "C" and grade != 10: continue # Math 10C only
                        if subj_cat == "Science" and grade == 10: # Science 10, 14, 10-4 don't fit grade//10 pattern well
                            if stream_suffix == " 10": course_name_candidate = "Science 10"
                            elif stream_suffix == " 14": course_name_candidate = "Science 14"
                            elif stream_suffix == " 10-4": course_name_candidate = "Science 10-4"
                            else: continue # Skip other suffixes for G10 science for now
                        elif subj_cat == "Science" and grade == 11:
                            # For G11 Science, let's be more specific, e.g. Bio 20, Chem 20, Phys 20
                            # This part is tricky for generic suggestion, depends on pathways
                            # Sticking to a simpler model for now, or user adds specifics.
                            # For simplicity, let's try to suggest ONE general science or a specific one.
                            if stream_suffix == " 20": course_name_candidate = "Science 20" # or Biology 20, etc.
                            elif stream_suffix == " 24": course_name_candidate = "Science 24"
                            elif stream_suffix == " 20-4": course_name_candidate = "Science 20-4"
                            else: continue
                        elif subj_cat == "Science" and grade == 12:
                             if stream_suffix == " 30": course_name_candidate = "Science 30" # or Biology 30, etc.
                             else: continue


                        credits = self.high_school_credits_db.get(course_name_candidate)
                        if credits:
                            course_mins_total = credits * CREDITS_TO_HOURS_PER_CREDIT * 60
                            periods_total_instances = math.ceil(course_mins_total / p_dur_min) if p_dur_min > 0 else 0
                            periods_per_week = math.ceil(periods_total_instances / weeks_course_duration_for_calc) if weeks_course_duration_for_calc > 0 else 0
                            periods_per_week = max(1, periods_per_week if periods_total_instances > 0 else 0)

                            if available_slots_per_term_week[term_num_suggest] >= periods_per_week:
                                if not any(c['name'] == course_name_candidate and c['grade_level'] == grade and c['term_assignment'] == term_num_suggest for c in suggested_this_pass):
                                    suggested_this_pass.append({
                                        'name': course_name_candidate, 'credits': credits, 'grade_level': grade,
                                        'subject_area': subj_cat, 'term_assignment': term_num_suggest,
                                        'periods_per_week_in_active_term': periods_per_week,
                                        # Fill other fields as in your original structure
                                        'assigned_teacher_name': None,
                                        'periods_per_year_total_instances': periods_total_instances,
                                        'scheduling_constraints_raw': "", 'parsed_constraints': [],
                                        '_is_suggestion': True, '_is_one_credit_buffer_item': False,
                                        '_is_one_credit_buffer_item_from_suggestion': False
                                    })
                                    available_slots_per_term_week[term_num_suggest] -= periods_per_week
                                    self._log_message(f"Suggest Engine (P1): Added {course_name_candidate} (Gr{grade}, {periods_per_week}p/wk) to Term {term_num_suggest}. Term slots left: {available_slots_per_term_week[term_num_suggest]}", "DEBUG")
                                    stream_found_for_subj = True
                                    break # Found one stream for this core subject for this grade in this term
                    if not stream_found_for_subj:
                         self._log_message(f"Suggest Engine (P1 Warning): Could not fit primary core {subj_cat} for Gr{grade} in Term {term_num_suggest} due to capacity.", "WARN")


                # Suggest other important courses for the grade
                for course_name_other, subj_other, term_pref_other in other_important_courses.get(grade, []):
                    term_to_try_other = term_pref_other if term_pref_other is not None else term_num_suggest
                    if term_to_try_other != term_num_suggest: continue # Only suggest if it's this course's preferred term OR if no preference matches current term

                    credits_other = self.high_school_credits_db.get(course_name_other)
                    if credits_other:
                        course_mins_total_other = credits_other * CREDITS_TO_HOURS_PER_CREDIT * 60
                        periods_total_instances_other = math.ceil(course_mins_total_other / p_dur_min) if p_dur_min > 0 else 0
                        periods_per_week_other = math.ceil(periods_total_instances_other / weeks_course_duration_for_calc) if weeks_course_duration_for_calc > 0 else 0
                        periods_per_week_other = max(1, periods_per_week_other if periods_total_instances_other > 0 else 0)

                        if available_slots_per_term_week[term_num_suggest] >= periods_per_week_other:
                             if not any(c['name'] == course_name_other and c['grade_level'] == grade and c['term_assignment'] == term_num_suggest for c in suggested_this_pass):
                                suggested_this_pass.append({
                                    'name': course_name_other, 'credits': credits_other, 'grade_level': grade,
                                    'subject_area': subj_other, 'term_assignment': term_num_suggest,
                                    'periods_per_week_in_active_term': periods_per_week_other,
                                    'assigned_teacher_name': None, 'periods_per_year_total_instances': periods_total_instances_other,
                                    'scheduling_constraints_raw': "", 'parsed_constraints': [],
                                    '_is_suggestion': True, '_is_one_credit_buffer_item': False,
                                     '_is_one_credit_buffer_item_from_suggestion': False
                                })
                                available_slots_per_term_week[term_num_suggest] -= periods_per_week_other
                                self._log_message(f"Suggest Engine (P1): Added {course_name_other} (Gr{grade}, {periods_per_week_other}p/wk) to Term {term_num_suggest}. Term slots left: {available_slots_per_term_week[term_num_suggest]}", "DEBUG")
                        else:
                            self._log_message(f"Suggest Engine (P1 Warning): Could not fit important {course_name_other} for Gr{grade} in Term {term_num_suggest} due to capacity.", "WARN")

        suggested_courses_all_grades.extend(suggested_this_pass)


        # --- Pass 2: Try to add alternative core streams if capacity allows ---
        # This is more complex because "which alternative" is school-specific.
        # For now, this pass can be kept simple or omitted if Pass 1 gives a good base.
        # A more advanced version would look at typical student pathways.
        # Current Pass 1 is already trying to pick the 'first' valid stream.

        # --- Pass 3: Fill remaining capacity with generic Option Slots ---
        self._log_message("Suggest Engine: Pass 3 - Filling with Option Slots", "INFO")
        option_block_priority = POSSIBLE_OPTION_BLOCK_SIZES # e.g., [5, 3, 1] or your defined constant

        for term_num_fill in range(1, num_terms + 1):
            option_slot_counter_term = 1
            self._log_message(f"Suggest Engine (P3): Term {term_num_fill} has {available_slots_per_term_week[term_num_fill]} p/wk capacity left for options.", "DEBUG")
            while available_slots_per_term_week[term_num_fill] >= min(option_block_priority, default=1): # Ensure smallest block can fit
                periods_for_this_option_slot = 0
                for block_size in option_block_priority:
                    if available_slots_per_term_week[term_num_fill] >= block_size:
                        periods_for_this_option_slot = block_size
                        break
                
                if periods_for_this_option_slot == 0: # No suitable block size fits
                    if available_slots_per_term_week[term_num_fill] > 0: # take remaining if any
                        periods_for_this_option_slot = math.floor(available_slots_per_term_week[term_num_fill])
                        if periods_for_this_option_slot == 0: break # really no room
                    else: break


                option_name = f"Option Slot {option_slot_counter_term} (Mixed Grade)"
                
                # Estimate credits (same logic as before)
                option_weeks_credits = weeks_course_duration_for_calc # Options usually run for the term duration
                total_hours_slot = (periods_for_this_option_slot * option_weeks_credits * p_dur_min) / 60.0
                option_credits_est = max(1, math.ceil(total_hours_slot / CREDITS_TO_HOURS_PER_CREDIT))
                # Refine common block credits
                if periods_for_this_option_slot == 1 and option_weeks_credits >= 15: option_credits_est = 1
                elif periods_for_this_option_slot == 3 and option_weeks_credits >= 15: option_credits_est = 3
                elif periods_for_this_option_slot == 5 and option_weeks_credits >= 15: option_credits_est = 5


                suggested_courses_all_grades.append({
                    'name': option_name, 'credits': option_credits_est, 'grade_level': "Mixed",
                    'subject_area': "Other", 'term_assignment': term_num_fill,
                    'periods_per_week_in_active_term': periods_for_this_option_slot,
                    'assigned_teacher_name': None,
                    'periods_per_year_total_instances': periods_for_this_option_slot * option_weeks_credits, # Approx
                    'scheduling_constraints_raw': "", 'parsed_constraints': [],
                    '_is_suggestion': True,
                    '_is_one_credit_buffer_item': option_credits_est == 1,
                     '_is_one_credit_buffer_item_from_suggestion': option_credits_est == 1
                })
                available_slots_per_term_week[term_num_fill] -= periods_for_this_option_slot
                self._log_message(f"Suggest Engine (P3): Added '{option_name}' to Term {term_num_fill} ({periods_for_this_option_slot} p/wk, est {option_credits_est}cr). Term slots left: {available_slots_per_term_week[term_num_fill]}", "DEBUG")
                option_slot_counter_term += 1
            
            if available_slots_per_term_week[term_num_fill] > 0:
                 self._log_message(f"Suggest Engine (P3 Info): Term {term_num_fill} has {available_slots_per_term_week[term_num_fill]:.2f} p/wk capacity remaining (too small for option blocks).", "INFO")

        return suggested_courses_all_grades

    def _edit_item_details(self, item_to_edit, get_item_details_func, item_name_singular):
        print(f"\n--- Editing {item_name_singular}: '{item_to_edit.get('name')}' ---")
        updated_item = get_item_details_func(defaults=copy.deepcopy(item_to_edit))
        if updated_item:
            self._log_message(f"'{item_to_edit.get('name')}' updated to '{updated_item.get('name')}'.", "INFO")
            return updated_item
        else:
            self._log_message(f"Editing for '{item_to_edit.get('name')}' cancelled or failed. Keeping original.", "WARN")
            return item_to_edit

    def _get_list_data(self, data_key, item_name_singular, item_name_plural, get_item_details_func):
        print(f"\n--- {item_name_plural.capitalize()} Information ---")
        current_items = copy.deepcopy(self.session_cache.get(data_key, []))
        if data_key == 'teachers_data':
            num_p_day_current = self.params.get('num_periods_per_day', 1)
            if not isinstance(num_p_day_current, int) or num_p_day_current <= 0: num_p_day_current = 1
            temp_reparsed_teachers = []
            for item_t in current_items:
                raw_avail_str_t = item_t.get('raw_availability_str', "")
                item_t['availability'] = parse_teacher_availability(raw_avail_str_t, num_p_day_current)
                temp_reparsed_teachers.append(item_t)
            current_items = temp_reparsed_teachers

        if data_key == 'courses_data_raw_input' and self.params.get('school_type') == 'High School' and not current_items:
            initial_suggestions = self._get_suggested_core_courses()
            if initial_suggestions:
                print("\n--- Suggested Core Courses & Option Slots (auto-filled based on setup) ---")
                for idx, sugg_item in enumerate(initial_suggestions):
                    print(f"  {idx+1}. {sugg_item['name']} (Grade: {sugg_item['grade_level']}, Credits: {sugg_item['credits']}, Subj: {sugg_item['subject_area']}, Term: {sugg_item['term_assignment']}, Pds/Wk: {sugg_item.get('periods_per_week_in_active_term')})")
                use_suggestions_key = f'{data_key}_include_suggestions_{random.randint(1000,9999)}'
                include_suggestions = self.get_input_with_default(use_suggestions_key, "Include these auto-filled suggestions in your course list?", str, lambda x: x.lower() in ['yes', 'no'], choices=['yes', 'no'])
                if include_suggestions.lower() == 'yes':
                    current_items.extend(initial_suggestions)
                    self._log_message(f"Added {len(initial_suggestions)} suggested courses/slots to the list.", "INFO")

        while True:
            print(f"\n--- Current {item_name_plural} ({len(current_items)}) ---")
            if data_key == 'courses_data_raw_input':
                grade_counts = defaultdict(int)
                for item in current_items:
                    grade = item.get('grade_level')
                    if isinstance(grade, int):
                        grade_counts[grade] += 1
                    elif isinstance(grade, str) and grade.lower() == "mixed":
                        grade_counts['Mixed'] += 1
                    else:
                        grade_counts[str(grade)] += 1

                grade_summary_parts = []
                sorted_grades = sorted(
                    grade_counts.keys(),
                    key=lambda g: (isinstance(g, str), str(g).lower() if isinstance(g, str) else g)
                )

                for g in sorted_grades:
                    grade_summary_parts.append(f"Grade {g}: {grade_counts[g]}")
                if grade_summary_parts:
                    print(f"  Summary: {', '.join(grade_summary_parts)}")
                else:
                    print("  Summary: No grade data to summarize.")


            if not current_items: print(f"No {item_name_plural} defined yet.")
            else:
                for idx, item in enumerate(current_items):
                    name_attr = item.get('name', f"Item {idx+1}"); details_str = ""
                    if data_key == 'teachers_data':
                        avail_str = item.get('raw_availability_str', "N/A");
                        if not avail_str: avail_str = "Always Available"
                        details_str = f"(Quals: {', '.join(item.get('qualifications',[]))}; Avail: {avail_str})"
                    elif data_key == 'courses_data_raw_input':
                        details_str = f"(Crs: {item.get('credits')}, Subj: {item.get('subject_area')}, Gr: {item.get('grade_level')}, Term: {item.get('term_assignment')}, P/Wk: {item.get('periods_per_week_in_active_term')})"
                    print(f"  {idx+1}. {name_attr} {details_str}")

            list_action_key = f'{data_key}_list_action_{random.randint(1000,9999)}'
            choices_for_list_action = ["Add new", "Edit existing", "Delete existing", "Clear all and start fresh", "Finish and use this list"]
            if not current_items: choices_for_list_action = ["Add new", "Finish (empty list)"]
            list_action = self.get_input_with_default(list_action_key, f"Action for {item_name_plural}", str, choices=choices_for_list_action)

            if list_action == "Add new":
                print(f"\n-- Adding new {item_name_singular} --")
                new_item_data = get_item_details_func(defaults=None)
                if new_item_data: current_items.append(new_item_data)
            elif list_action == "Edit existing" and current_items:
                edit_idx_key = f'{data_key}_edit_idx_{random.randint(1000,9999)}'
                edit_idx_str = self.get_input_with_default(edit_idx_key, f"Enter number of the {item_name_singular} to edit", str)
                try:
                    edit_idx = int(edit_idx_str) - 1
                    if 0 <= edit_idx < len(current_items):
                        edited_item = self._edit_item_details(current_items[edit_idx], get_item_details_func, item_name_singular)
                        current_items[edit_idx] = edited_item
                    else: print("Invalid number.")
                except ValueError: print("Invalid input for number.")
            elif list_action == "Delete existing" and current_items:
                del_idx_key = f'{data_key}_del_idx_{random.randint(1000,9999)}'
                del_idx_str = self.get_input_with_default(del_idx_key, f"Enter number of the {item_name_singular} to delete", str)
                try:
                    del_idx = int(del_idx_str) - 1
                    if 0 <= del_idx < len(current_items):
                        deleted_item_name = current_items.pop(del_idx).get('name', 'Unknown item')
                        print(f"'{deleted_item_name}' deleted.")
                    else: print("Invalid number.")
                except ValueError: print("Invalid input for number.")
            elif list_action == "Clear all and start fresh": current_items = []; print(f"All {item_name_plural} cleared.")
            elif list_action == "Finish and use this list" or list_action == "Finish (empty list)": break

        self.session_cache[data_key] = current_items
        print(f"\nFinalized {item_name_plural} list with {len(current_items)} entries.")

        if data_key == 'courses_data_raw_input' and self.params.get('school_type') == 'High School':
            self.course_details_map = {c['name']: c for c in current_items if c}
            self.courses_data_master = copy.deepcopy(current_items)
        elif data_key == 'subjects_data':
             self.subjects_data = copy.deepcopy(current_items)

        return current_items

    def _get_teacher_details(self, defaults=None):
        name = self.get_input_with_default(None, "Teacher Name", str, lambda x: len(x) > 0)
        qualifications = []
        print(f"Enter qualified subjects for {name} (comma-separated numbers or names from list, or 'done'):")
        while True:
            for i, subj_name in enumerate(QUALIFIABLE_SUBJECTS): print(f"  {i+1}. {subj_name}{' (already qualified)' if subj_name in qualifications else ''}")
            q_input_str = input(f"Add qualifications for {name} (e.g., 1,3 or Math,English, or 'done'): ").strip()
            if q_input_str.lower() == 'done': break
            if not q_input_str: continue
            temp_qual_round, valid_q_input = [], True
            for q_part in q_input_str.split(','):
                q_part = q_part.strip(); q_idx = -1; matched_subj_text = None
                if not q_part: continue
                try: q_idx = int(q_part) - 1
                except ValueError: matched_subj_text = next((s for s in QUALIFIABLE_SUBJECTS if s.lower() == q_part.lower()), None)
                subj_to_add = None
                if 0 <= q_idx < len(QUALIFIABLE_SUBJECTS): subj_to_add = QUALIFIABLE_SUBJECTS[q_idx]
                elif matched_subj_text: subj_to_add = matched_subj_text
                if subj_to_add:
                    if subj_to_add not in qualifications: temp_qual_round.append(subj_to_add)
                    else: print(f"  Note: {subj_to_add} already selected.")
                else: print(f"Invalid subject: {q_part}"); valid_q_input = False; break
            if valid_q_input: qualifications.extend(q for q in temp_qual_round if q not in qualifications)
            else: print("  Error in input. Please re-enter this set of qualifications.")
            print(f"  Current qualifications for {name}: {', '.join(qualifications) if qualifications else 'None'}")

        num_p_day_for_parse = self.params.get('num_periods_per_day', 1)
        if not isinstance(num_p_day_for_parse, int) or num_p_day_for_parse <= 0: num_p_day_for_parse = 1
        availability_str_input = self.get_input_with_default(None, f"Teacher {name} Availability (e.g., 'Unavailable Mon P1-P2', blank if always available)", str, allow_empty=True)
        parsed_availability_map = parse_teacher_availability(availability_str_input, num_p_day_for_parse)
        available_slots_count = 0
        for day_check in DAYS_OF_WEEK:
            for period_check in range(num_p_day_for_parse):
                if parsed_availability_map.get(day_check, {}).get(period_check, False): available_slots_count += 1
        print(f"  INFO: Teacher {name} has {available_slots_count} available slots per week (based on {num_p_day_for_parse} periods/day).")
        if available_slots_count == 0: print(f"  CRITICAL WARNING: Teacher {name} has NO available teaching slots!")
        elif available_slots_count < MIN_PREP_BLOCKS_PER_WEEK: print(f"  CRITICAL WARNING: Teacher {name} has {available_slots_count} slots, < {MIN_PREP_BLOCKS_PER_WEEK} required prep blocks!")
        elif available_slots_count == MIN_PREP_BLOCKS_PER_WEEK: print(f"  WARNING: Teacher {name} has {available_slots_count} slots, matching {MIN_PREP_BLOCKS_PER_WEEK} prep. 0 teaching periods assignable.")
        return {'name': name, 'qualifications': qualifications, 'availability': parsed_availability_map, 'raw_availability_str': availability_str_input}

    def get_teachers_data(self):
        self.teachers_data = self._get_list_data('teachers_data', 'teacher', 'teachers', self._get_teacher_details)

    def _get_elementary_subject_details(self, defaults=None):
        s_name = self.get_input_with_default(None, "Subject Name", str, lambda x: len(x) > 0)
        p_week = self.get_input_with_default(None, f"Periods/week for {s_name}", int, lambda x: x > 0)
        constraints_raw = self.get_input_with_default(None, f"Scheduling constraints for {s_name} (e.g., 'NOT P1')", str, allow_empty=True)
        subj_area = s_name
        if s_name not in QUALIFIABLE_SUBJECTS:
            print(f"Subject '{s_name}' not standard. Categorize for teacher quals:")
            subj_area = self.get_input_with_default(None, f"Categorize '{s_name}' as", str, lambda x: x in QUALIFIABLE_SUBJECTS, choices=QUALIFIABLE_SUBJECTS)
        num_p_day_for_parse = self.params.get('num_periods_per_day', 1)
        if not isinstance(num_p_day_for_parse, int) or num_p_day_for_parse <= 0: num_p_day_for_parse = 1
        return {'name': s_name, 'periods_per_week': p_week, 'assigned_teacher_name': None, 'subject_area': subj_area, 'scheduling_constraints_raw': constraints_raw, 'parsed_constraints': parse_scheduling_constraint(constraints_raw, num_p_day_for_parse)}

    def get_elementary_subjects(self):
        self.subjects_data = self._get_list_data('subjects_data', 'subject', 'subjects', self._get_elementary_subject_details)

    def _get_high_school_course_details(self, defaults=None):
        if defaults is None: defaults = {}
        num_p_day = self.params.get('num_periods_per_day', 1)
        if not isinstance(num_p_day, int) or num_p_day <= 0: num_p_day = 1
        p_dur_min = self.params.get('period_duration_minutes', 1)
        if not isinstance(p_dur_min, int) or p_dur_min <= 0: p_dur_min = 60

        weeks_course_dur_for_calc = self.params.get('weeks_per_term', 18)
        if self.params.get('scheduling_model') == "Full Year":
            weeks_course_dur_for_calc = self.params.get('num_instructional_weeks', 36)
        if not isinstance(weeks_course_dur_for_calc, int) or weeks_course_dur_for_calc <= 0: weeks_course_dur_for_calc = 18

        prompt_key_suffix = f"_{random.randint(1000,9999)}"
        course_name_default = defaults.get('name')
        course_name = self.get_input_with_default(f"course_name{prompt_key_suffix}", "Course Name", str, lambda x: len(x) > 0, default_value_override=course_name_default)

        grade_level_default_str = str(defaults.get('grade_level', '10'))
        if isinstance(defaults.get('grade_level'), str) and defaults.get('grade_level').lower() == "mixed":
            grade_level_default_str = "Mixed"

        grade_level_str = self.get_input_with_default(f"grade_level{prompt_key_suffix}", f"Grade Level for {course_name} (e.g. 10, 11, 12, or Mixed)", str, default_value_override=grade_level_default_str)
        grade_level = "Mixed" if grade_level_str.lower() == "mixed" else (int(grade_level_str) if grade_level_str.isdigit() else "Mixed")

        subject_area_default = defaults.get('subject_area')
        subj_area = self.get_input_with_default(f"subject_area{prompt_key_suffix}", f"Subject area for '{course_name}'", str, lambda x: x in QUALIFIABLE_SUBJECTS, choices=QUALIFIABLE_SUBJECTS, default_value_override=subject_area_default)

        credits_default = defaults.get('credits')
        credits_from_db = self.high_school_credits_db.get(course_name)
        credits = credits_from_db if credits_from_db is not None and not course_name.lower().startswith("option slot") else credits_default

        if credits is None: credits = self.get_input_with_default(f"credits{prompt_key_suffix}", f"Credits for {course_name}", int, lambda x: x > 0)
        else: credits = self.get_input_with_default(f"credits{prompt_key_suffix}", f"Credits for {course_name}", int, lambda x: x > 0, default_value_override=credits)

        if credits is None: print(f"ERROR: Credits not determined for {course_name}."); return None
        if credits != credits_from_db and not course_name.lower().startswith("option slot"): self.high_school_credits_db[course_name] = credits

        is_one_credit_now = (credits == 1)
        if is_one_credit_now and not defaults.get('_is_one_credit_buffer_item_from_suggestion', False) and not course_name.lower().startswith("option slot"):
            return {'name': course_name, 'credits': credits, 'subject_area': subj_area, 'grade_level': grade_level, '_is_one_credit_buffer_item': True}

        periods_week_term = defaults.get('periods_per_week_in_active_term')
        if periods_week_term is None:
            course_mins = credits * CREDITS_TO_HOURS_PER_CREDIT * 60
            periods_year_calc = math.ceil(course_mins / p_dur_min) if p_dur_min > 0 else course_mins
            periods_week_term = math.ceil(periods_year_calc / weeks_course_dur_for_calc) if weeks_course_dur_for_calc > 0 else periods_year_calc
            periods_week_term = max(1, periods_week_term if periods_year_calc > 0 else 0)
            print(f"  INFO: Calculated {periods_week_term} periods/week for {course_name} ({credits} credits, based on {weeks_course_dur_for_calc} weeks duration).")
        else:
             print(f"  INFO: Using {periods_week_term} periods/week for {course_name} (from suggestion/default).")

        periods_year = defaults.get('periods_per_year_total_instances')
        if periods_year is None:
            periods_year = periods_week_term * weeks_course_dur_for_calc

        constraints_default = defaults.get('scheduling_constraints_raw', "")
        raw_constr = self.get_input_with_default(f"constraints{prompt_key_suffix}", f"Constraints for {course_name}", str, allow_empty=True, default_value_override=constraints_default)
        parsed_constr = parse_scheduling_constraint(raw_constr, num_p_day)
        assign_slots_count = sum(1 for c in parsed_constr if c.get('type') == 'ASSIGN')
        if assign_slots_count > 0 and assign_slots_count != periods_week_term:
            self._log_message(f"WARN: For {course_name}, ASSIGNed slots ({assign_slots_count}) != calc p/wk ({periods_week_term}). Using ASSIGN count for p/wk.", "WARN")
            periods_week_term = assign_slots_count
            periods_year = periods_week_term * weeks_course_dur_for_calc

        term_assignment_default = defaults.get('term_assignment', 1)
        term_assign = term_assignment_default
        if self.params.get('num_terms',1) > 1:
            term_assign = self.get_input_with_default(f"term_assignment{prompt_key_suffix}", f"Assign {course_name} to term (1-{self.params['num_terms']})", int, lambda x: 1 <= x <= self.params['num_terms'], default_value_override=term_assignment_default)
        elif self.params.get('num_terms',1) == 1: term_assign = 1

        return {'name': course_name, 'credits': credits, 'grade_level': grade_level,
                'assigned_teacher_name': None, 'subject_area': subj_area,
                'periods_per_year_total_instances': periods_year, 'periods_per_week_in_active_term': periods_week_term,
                'scheduling_constraints_raw': raw_constr, 'parsed_constraints': parsed_constr, 'term_assignment': term_assign,
                '_is_one_credit_buffer_item': is_one_credit_now and defaults.get('_is_one_credit_buffer_item_from_suggestion', False)}

    def get_high_school_courses(self):
        self._log_message("--- High School Course Management ---", "DEBUG")
        self.high_school_credits_db = copy.deepcopy(self.session_cache.get('high_school_credits_db', HIGH_SCHOOL_COURSE_CREDITS_TEMPLATE))

        if not self.session_cache.get('hs_credit_db_modified_once', False):
            print("Current HS Course Credits DB (synced with template, preserving previous user changes):")
            [print(f"  {c}: {cr}") for c, cr in sorted(self.high_school_credits_db.items())]
            if self.get_input_with_default('modify_credit_db_choice', "Further modify credit DB for this session?", str, lambda x: x.lower() in ['yes','no'], choices=['yes','no']).lower() == 'yes':
                while True:
                    c_name = input("Course name to add/modify credits (or 'done'): ").strip()
                    if c_name.lower() == 'done': break
                    if not c_name: continue
                    try:
                        c_cred = int(input(f"Credits for {c_name}: "))
                        if c_cred <=0: print("Credits must be positive."); continue
                        self.high_school_credits_db[c_name] = c_cred; print(f"'{c_name}' updated to {c_cred} credits in DB for this session.")
                    except ValueError: print("Invalid credit number.")
                self.session_cache['hs_credit_db_modified_once'] = True
                self.session_cache['high_school_credits_db'] = copy.deepcopy(self.high_school_credits_db)

        defined_courses_from_helper = self._get_list_data('courses_data_raw_input', 'course/block', 'courses/blocks', self._get_high_school_course_details)

        temp_courses_data = []
        one_credit_courses_buffer = copy.deepcopy(self.session_cache.get('one_credit_courses_buffer', []))
        newly_defined_one_credits_this_round = []

        for item in defined_courses_from_helper:
            if item is None: continue
            if item.get('_is_one_credit_buffer_item'):
                if not any(b['name'] == item['name'] for b in one_credit_courses_buffer + newly_defined_one_credits_this_round):
                    newly_defined_one_credits_this_round.append(item)
            else: temp_courses_data.append(item)

        for nc_item in newly_defined_one_credits_this_round:
            if not any(b['name'] == nc_item['name'] for b in one_credit_courses_buffer):
                one_credit_courses_buffer.append(nc_item)

        if one_credit_courses_buffer:
            self._log_message("\n--- 1-Credit Course Grouping ---", "DEBUG")
            while one_credit_courses_buffer:
                print("\nRemaining 1-credit courses to group:");
                for idx, c_info in enumerate(one_credit_courses_buffer): print(f"  {idx+1}. {c_info['name']} (Subj: {c_info.get('subject_area', 'N/A')}, Grade: {c_info.get('grade_level', 'N/A')})")
                group_now_key = f"one_credit_proceed_grouping_{random.randint(1000,9999)}"
                if self.get_input_with_default(group_now_key, "Group some now?", str, lambda x: x.lower() in ['yes', 'no'], choices=['yes','no']).lower() != 'yes': break
                group_size_key = f"one_credit_group_size_{random.randint(1000,9999)}"
                group_size_str = self.get_input_with_default(group_size_key, f"How many to group (e.g., 3, or 0 to stop)", str, allow_empty=True)
                try:
                    group_size = int(group_size_str) if group_size_str else 3
                    if group_size == 0: break
                    if not (1 < group_size <= len(one_credit_courses_buffer)): print(f"Invalid group size."); continue
                except ValueError: print("Invalid number."); continue
                indices_key = f"one_credit_select_indices_{random.randint(1000,9999)}"
                indices_str = self.get_input_with_default(indices_key, f"Select {group_size} by number (comma-separated)", str)
                try:
                    selected_indices = [int(x.strip())-1 for x in indices_str.split(',')]
                    if not(len(selected_indices) == group_size and all(0 <= i < len(one_credit_courses_buffer) for i in selected_indices) and len(set(selected_indices)) == group_size):
                        print("Invalid selection."); continue
                except ValueError: print("Invalid input."); continue
                block_name_key = f"block_name_one_credit_{random.randint(1000,9999)}"
                block_name = self.get_input_with_default(block_name_key, "Name for this new block", str, lambda x: len(x)>0)
                block_courses_details = [one_credit_courses_buffer[i] for i in sorted(selected_indices, reverse=False)]
                block_grade_levels = set(c.get('grade_level') for c in block_courses_details if c.get('grade_level') and c.get('grade_level') != "Mixed")
                block_grade_level_final = "Mixed"
                if len(block_grade_levels) == 1: block_grade_level_final = list(block_grade_levels)[0]
                elif not block_grade_levels: block_grade_level_final = "Mixed"
                else:
                    block_grade_key = f"block_grade_one_credit_{random.randint(1000,9999)}"
                    block_grade_level_final_str = self.get_input_with_default(block_grade_key, f"Grade Level for Block '{block_name}'", str, allow_empty=False)
                    if block_grade_level_final_str.lower() == "mixed": block_grade_level_final = "Mixed"
                    else:
                        try: block_grade_level_final = int(block_grade_level_final_str)
                        except ValueError: block_grade_level_final = "Mixed"
                for i in sorted(selected_indices, reverse=True): one_credit_courses_buffer.pop(i)
                block_credits = sum(c['credits'] for c in block_courses_details)
                block_subj_key = f"block_subj_one_credit_{random.randint(1000,9999)}"
                block_subject_area = self.get_input_with_default(block_subj_key, f"Subject area for block '{block_name}'", str, lambda x: x in QUALIFIABLE_SUBJECTS, choices=QUALIFIABLE_SUBJECTS)
                num_p_day_local = self.params.get('num_periods_per_day', 1); p_dur_min_local = self.params.get('period_duration_minutes', 1)

                weeks_course_dur_local_block = self.params.get('weeks_per_term', 18)
                if self.params.get('scheduling_model') == "Full Year":
                    weeks_course_dur_local_block = self.params.get('num_instructional_weeks', 36)
                if not isinstance(weeks_course_dur_local_block, int) or weeks_course_dur_local_block <= 0: weeks_course_dur_local_block = 18

                if not isinstance(num_p_day_local, int) or num_p_day_local <= 0: num_p_day_local = 1
                if not isinstance(p_dur_min_local, int) or p_dur_min_local <= 0: p_dur_min_local = 1

                block_mins = block_credits * CREDITS_TO_HOURS_PER_CREDIT * 60
                block_periods_year = math.ceil(block_mins / p_dur_min_local) if p_dur_min_local > 0 else block_mins
                block_periods_week = math.ceil(block_periods_year / weeks_course_dur_local_block) if weeks_course_dur_local_block > 0 else block_periods_year
                block_periods_week = max(1, block_periods_week if block_periods_year > 0 else 0)
                block_constr_key = f"block_constr_one_credit_{random.randint(1000,9999)}"
                raw_constr_block = self.get_input_with_default(block_constr_key, f"Constraints for block '{block_name}'", str, allow_empty=True)
                parsed_constr_block = parse_scheduling_constraint(raw_constr_block, num_p_day_local)
                assign_slots_block = sum(1 for c in parsed_constr_block if c.get('type') == 'ASSIGN')
                if assign_slots_block > 0 and assign_slots_block != block_periods_week: block_periods_week = assign_slots_block; block_periods_year = block_periods_week * weeks_course_dur_local_block
                term_assign_block = 1
                block_term_key = f"block_term_one_credit_{random.randint(1000,9999)}"
                if self.params.get('num_terms',1) > 1: term_assign_block = self.get_input_with_default(block_term_key, f"Assign block to term (1-{self.params['num_terms']})", int, lambda x: 1<=x<=self.params['num_terms'])

                temp_courses_data.append({'name': block_name + f" (contains: {', '.join(c['name'] for c in block_courses_details)})",
                                      'credits': block_credits, 'grade_level': block_grade_level_final,
                                      'assigned_teacher_name': None, 'subject_area': block_subject_area,
                                      'periods_per_year_total_instances': block_periods_year,
                                      'periods_per_week_in_active_term': block_periods_week,
                                      'scheduling_constraints_raw': raw_constr_block,
                                      'parsed_constraints': parsed_constr_block,
                                      'term_assignment': term_assign_block})
                self._log_message(f"Block '{block_name}' created.", "DEBUG")
                if not one_credit_courses_buffer: self._log_message("All 1-credit courses addressed.", "INFO"); break

        self.session_cache['one_credit_courses_buffer'] = one_credit_courses_buffer
        self.courses_data_master = copy.deepcopy(temp_courses_data)
        self.course_details_map = {c['name']: c for c in self.courses_data_master if c}
        self.session_cache['courses_data'] = copy.deepcopy(self.courses_data_master)
        if one_credit_courses_buffer: self._log_message(f"Warning: {len(one_credit_courses_buffer)} 1-credit courses ungrouped.", "WARN")

    def get_program_specific_constraints(self):
        self._log_message("--- Program Specific Constraints ---", "DEBUG")
        if self.params.get('school_type') == 'High School':
            has_cree_courses = any(
                "cree" in course.get('name', '').lower() or course.get('subject_area', '').lower() == "cree"
                for course in self.courses_data_master
            )
            if has_cree_courses:
                cree_constraint_choice = self.get_input_with_default(
                    'enforce_cree_per_term_choice',
                    "Do you want to enforce that at least one Cree class is scheduled per term?",
                    str,
                    lambda x: x.lower() in ['yes', 'no'],
                    choices=['yes', 'no'],
                    default_value_override=self.session_cache.get('enforce_cree_per_term_choice', 'no')
                )
                self.params['enforce_cree_per_term'] = cree_constraint_choice.lower() == 'yes'
                self.session_cache['enforce_cree_per_term_choice'] = cree_constraint_choice
                self._log_message(f"Enforce Cree per term: {self.params['enforce_cree_per_term']}", "INFO")
            else:
                self.params['enforce_cree_per_term'] = False
                self.session_cache['enforce_cree_per_term_choice'] = 'no'
                self._log_message("No Cree courses defined, so 'enforce_cree_per_term' constraint is N/A and set to False.", "INFO")


    def get_general_constraints(self):
        self.cohort_constraints = self._get_list_data('cohort_constraints_list', 'cohort constraint group', 'cohort constraints', self._get_single_cohort_constraint_details)

    def _get_single_cohort_constraint_details(self, defaults=None):
        all_course_names_in_system = [c['name'].split(' (')[0].strip() for c in self.courses_data_master if c]
        if not all_course_names_in_system: print("No courses defined yet."); return None
        print("Available course names (base names for blocks):"); [print(f"  {i+1}. {name}") for i, name in enumerate(all_course_names_in_system)]
        while True:
            constraint_str_key = f"cohort_constraint_input_{random.randint(1000,9999)}"
            constraint_str = self.get_input_with_default(constraint_str_key, "Enter clashing courses (comma-separated names/numbers)", str, lambda x: len(x.split(',')) >= 2 )
            if not constraint_str: return None
            clashing_inputs = [name.strip() for name in constraint_str.split(',') if name.strip()]
            if len(clashing_inputs) < 2: print("Need at least two course names/numbers."); continue
            selected_names, valid_sel = [], True
            for item in clashing_inputs:
                try:
                    idx = int(item) - 1
                    if 0 <= idx < len(all_course_names_in_system): selected_names.append(all_course_names_in_system[idx])
                    else: print(f"Invalid course number: {item}"); valid_sel = False; break
                except ValueError:
                    matched_name = next((cn for cn in all_course_names_in_system if item.lower() == cn.lower()), None)
                    if matched_name: selected_names.append(matched_name)
                    else:
                        partial = [cn for cn in all_course_names_in_system if item.lower() in cn.lower()]
                        if len(partial)==1: selected_names.append(partial[0]); print(f"Interpreted '{item}' as '{partial[0]}'.")
                        elif len(partial)>1: print(f"Ambiguous '{item}'. Matches: {', '.join(partial)}."); valid_sel=False; break
                        else: print(f"Course name not found: {item}"); valid_sel=False; break
            if not valid_sel: continue
            if len(set(selected_names)) < 2: print("Constraint needs at least two *different* courses."); continue
            self._log_message(f"Cohort constraint: {selected_names} should not overlap.", "DEBUG"); return selected_names

    def _is_teacher_qualified(self, teacher_obj_or_name, subject_area):
        teacher_obj = None
        if isinstance(teacher_obj_or_name, str):
            teacher_obj = next((t for t in self.teachers_data if t['name'] == teacher_obj_or_name), None)
        elif isinstance(teacher_obj_or_name, dict):
            teacher_obj = teacher_obj_or_name

        if not teacher_obj: return False
        if subject_area == "Other": return True
        return subject_area in teacher_obj.get('qualifications', [])

    def _find_qualified_teacher(self, subject_area, day_name, period_idx, teacher_busy_map, teacher_current_load, teacher_max_load, existing_teacher_name=None):
        if existing_teacher_name:
            teacher_obj = next((t for t in self.teachers_data if t['name'] == existing_teacher_name), None)
            if teacher_obj and self._is_teacher_qualified(teacher_obj, subject_area) and \
               teacher_obj.get('availability', {}).get(day_name, {}).get(period_idx, False) and \
               (day_name, period_idx) not in teacher_busy_map.get(existing_teacher_name, set()) and \
               teacher_current_load.get(existing_teacher_name, 0) < teacher_max_load.get(existing_teacher_name, 0):
                return existing_teacher_name

        available_teachers = []
        for teacher in self.teachers_data:
            if self._is_teacher_qualified(teacher, subject_area) and \
               teacher.get('availability', {}).get(day_name, {}).get(period_idx, False) and \
               (day_name, period_idx) not in teacher_busy_map.get(teacher['name'], set()) and \
               teacher_current_load.get(teacher['name'], 0) < teacher_max_load.get(teacher['name'], 0):
                available_teachers.append(teacher['name'])

        return random.choice(available_teachers) if available_teachers else None

    def _get_teacher_object_by_name(self, teacher_name):
        return next((t for t in self.teachers_data if t['name'] == teacher_name), None)

    def _get_course_details_by_name(self, course_name_in_schedule):
        direct_match = self.course_details_map.get(course_name_in_schedule)
        if direct_match:
            return direct_match
        base_course_name = course_name_in_schedule.split(' (')[0].strip()
        return self.course_details_map.get(base_course_name)


    def calculate_schedule_cost(self, schedule, items_by_term_for_cost_calc):
        cost = 0
        num_p_day = self.params.get('num_periods_per_day', 1)
        num_terms = self.params.get('num_terms', 1)
        num_tracks = self.params.get('num_concurrent_tracks_per_period', 1)
        period_duration = self.params.get('period_duration_minutes', 0) # Fetch period duration

        teacher_assignments_per_slot = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
        teacher_total_periods_taught_per_term = defaultdict(lambda: defaultdict(int))

        all_scheduled_instances = []

        for term_idx, term_data in schedule.items():
            for day_name, day_slots in term_data.items():
                for period_idx, period_tracks in enumerate(day_slots):
                    for track_idx, slot_content in enumerate(period_tracks):
                        if slot_content and slot_content[0] and slot_content[1]:
                            course_name, teacher_name = slot_content
                            all_scheduled_instances.append((term_idx, day_name, period_idx, track_idx, course_name, teacher_name))

                            if teacher_name in teacher_assignments_per_slot[term_idx][day_name][period_idx]:
                                cost += PENALTY_HARD_CONSTRAINT_VIOLATION
                                self._log_message(f"COST: Teacher {teacher_name} double booked in T{term_idx} {day_name} P{period_idx+1}", "TRACE")
                            teacher_assignments_per_slot[term_idx][day_name][period_idx].add(teacher_name)

                            teacher_total_periods_taught_per_term[term_idx][teacher_name] += 1

                            teacher_obj = self._get_teacher_object_by_name(teacher_name)
                            if teacher_obj and not teacher_obj.get('availability', {}).get(day_name, {}).get(period_idx, False):
                                cost += PENALTY_HARD_CONSTRAINT_VIOLATION
                                self._log_message(f"COST: Teacher {teacher_name} not available for {course_name} in T{term_idx} {day_name} P{period_idx+1}", "TRACE")

                            course_details = self._get_course_details_by_name(course_name)
                            if course_details and not self._is_teacher_qualified(teacher_name, course_details.get('subject_area')):
                                cost += PENALTY_TEACHER_QUALIFICATION
                                self._log_message(f"COST: Teacher {teacher_name} not qualified for {course_name} (Subj: {course_details.get('subject_area')})", "TRACE")

                            if course_details:
                                for constr in course_details.get('parsed_constraints', []):
                                    if constr['type'] == 'NOT' and \
                                       (constr['day'] is None or constr['day'] == day_name) and \
                                       constr['period'] == period_idx:
                                        cost += PENALTY_HARD_CONSTRAINT_VIOLATION
                                        self._log_message(f"COST: Course {course_name} violates NOT constraint in T{term_idx} {day_name} P{period_idx+1}", "TRACE")

        for term_idx in range(1, num_terms + 1):
            for day_name in DAYS_OF_WEEK:
                for period_idx in range(num_p_day):
                    courses_in_this_slot_all_tracks = []
                    for track_idx in range(num_tracks):
                        slot_val = schedule.get(term_idx,{}).get(day_name,[])[period_idx][track_idx] if period_idx < len(schedule.get(term_idx,{}).get(day_name,[])) else None
                        if slot_val and slot_val[0]:
                            courses_in_this_slot_all_tracks.append(slot_val[0].split(' (')[0].strip())

                    for clash_group in self.cohort_constraints:
                        present_clashing_courses = [c for c in courses_in_this_slot_all_tracks if c in clash_group]
                        if len(present_clashing_courses) > 1:
                            cost += PENALTY_COHORT_CLASH * (len(present_clashing_courses) -1)
                            self._log_message(f"COST: Cohort clash in T{term_idx} {day_name} P{period_idx+1} involving {present_clashing_courses}", "TRACE")

        for term_idx_prep in range(1, num_terms + 1):
            for teacher in self.teachers_data:
                teacher_name = teacher['name']
                total_available_slots_this_teacher = 0
                for day_avail in DAYS_OF_WEEK:
                    for p_avail in range(num_p_day):
                        if teacher.get('availability', {}).get(day_avail, {}).get(p_avail, False):
                            total_available_slots_this_teacher += 1

                periods_taught_this_term = teacher_total_periods_taught_per_term[term_idx_prep].get(teacher_name, 0)
                prep_periods = total_available_slots_this_teacher - periods_taught_this_term
                if prep_periods < MIN_PREP_BLOCKS_PER_WEEK:
                    cost += PENALTY_INSUFFICIENT_PREP * (MIN_PREP_BLOCKS_PER_WEEK - prep_periods)
                    self._log_message(f"COST: Teacher {teacher_name} has {prep_periods} prep in T{term_idx_prep} (needs {MIN_PREP_BLOCKS_PER_WEEK})", "TRACE")

        if self.params.get('school_type') == 'High School':
            for term_idx_gs in range(1, num_terms + 1):
                for grade_to_check in GRADES_REQUIRING_FULL_SCHEDULE:
                    unmet_slots_for_grade_this_term = 0
                    for day_gs in DAYS_OF_WEEK:
                        for period_gs in range(num_p_day):
                            has_class_for_grade = False
                            for track_gs in range(num_tracks):
                                scheduled_item_tuple = schedule.get(term_idx_gs,{}).get(day_gs,[])[period_gs][track_gs] if period_gs < len(schedule.get(term_idx_gs,{}).get(day_gs,[])) else None
                                if scheduled_item_tuple and scheduled_item_tuple[0]:
                                    course_details_gs = self._get_course_details_by_name(scheduled_item_tuple[0])
                                    if course_details_gs:
                                        item_grade_level = course_details_gs.get('grade_level')
                                        if item_grade_level == grade_to_check or str(item_grade_level).lower() == "mixed":
                                            has_class_for_grade = True; break
                            if not has_class_for_grade:
                                unmet_slots_for_grade_this_term += 1
                    if unmet_slots_for_grade_this_term > 0:
                        cost += PENALTY_UNMET_GRADE_SLOT * unmet_slots_for_grade_this_term
                        self._log_message(f"COST: Grade {grade_to_check} has {unmet_slots_for_grade_this_term} unmet slots in T{term_idx_gs}", "TRACE")

            if self.params.get('enforce_cree_per_term', False):
                for term_idx_cree in range(1, num_terms + 1):
                    has_cree_this_term = False
                    for inst_term_cree, _, _, _, course_name_sch, _ in all_scheduled_instances:
                        if term_idx_cree == inst_term_cree:
                            course_details_cree = self._get_course_details_by_name(course_name_sch)
                            if course_details_cree and course_details_cree.get('subject_area', '').lower() == 'cree':
                                has_cree_this_term = True
                                break
                    if not has_cree_this_term:
                        cost += PENALTY_MISSING_CREE_PER_TERM
                        self._log_message(f"COST: Term {term_idx_cree} is missing a scheduled Cree class.", "TRACE")


        for term_idx_cp, courses_in_term_master in items_by_term_for_cost_calc.items():
            for course_master_detail in courses_in_term_master:
                required_periods = course_master_detail.get('periods_to_schedule_this_week', 0)
                actual_placed_periods = 0
                for inst_term, _, _, _, course_name_sch, _ in all_scheduled_instances:
                    # Ensure comparison with the master course name and its assigned term
                    if course_master_detail.get('term_assignment') == inst_term and \
                       course_name_sch == course_master_detail['name']:
                        actual_placed_periods +=1

                if actual_placed_periods < required_periods:
                    cost += PENALTY_UNPLACED_COURSE_PERIOD * (required_periods - actual_placed_periods)
                    self._log_message(f"COST (Unplaced): Course {course_master_detail['name']} T{course_master_detail.get('term_assignment')} needs {required_periods}, has {actual_placed_periods}", "TRACE")

        for term_idx_pref, day_data_pref in schedule.items():
            for day_name_pref, day_slots_pref in day_data_pref.items():
                for period_idx_pref, period_tracks_pref in enumerate(day_slots_pref):
                    for track_idx_pref, slot_content_pref in enumerate(period_tracks_pref):
                        if slot_content_pref and slot_content_pref[0]:
                            course_name_p, _ = slot_content_pref
                            course_details_p = self._get_course_details_by_name(course_name_p)
                            if course_details_p:
                                credits_p = course_details_p.get('credits')
                                is_cts_p = course_details_p.get('subject_area', '').upper() == "CTS"
                                is_mwf_day = day_name_pref in ["Monday", "Wednesday", "Friday"]
                                is_tth_day = day_name_pref in ["Tuesday", "Thursday"]

                                if credits_p == 3 and not is_mwf_day:
                                    cost += PENALTY_COURSE_NOT_IN_PREFERRED_SLOT_TYPE
                                if is_cts_p and not is_tth_day:
                                    cost += PENALTY_COURSE_NOT_IN_PREFERRED_SLOT_TYPE

        course_offering_periods = defaultdict(list)
        for inst_term, _, inst_period, _, inst_course_name, inst_teacher_name in all_scheduled_instances:
            inst_course_base_name = inst_course_name.split(' (')[0].strip()
            offering_key = (inst_term, inst_course_base_name, inst_teacher_name)
            course_offering_periods[offering_key].append(inst_period)

        for offering_key, period_indices_list in course_offering_periods.items():
            if not period_indices_list or len(period_indices_list) <= 1:
                continue

            unique_periods_for_offering = set(period_indices_list)
            if len(unique_periods_for_offering) > 1:
                term_k, course_k, teacher_k = offering_key
                cost += PENALTY_COURSE_PERIOD_INCONSISTENCY * (len(unique_periods_for_offering) - 1)
                self._log_message(f"COST (Period Inconsistency): Course '{course_k}' (T: {teacher_k}, Term: {term_k}) uses {len(unique_periods_for_offering)} different periods: {sorted(list(unique_periods_for_offering))}", "TRACE")

        # --- START: New Penalty for Credit-Minutes Mismatch ---
        if period_duration > 0: # Only apply if period duration is valid
            course_offering_num_periods_scheduled = defaultdict(int)
            # Populate this by counting instances for each offering
            for inst_term, _, _, _, inst_course_name, inst_teacher_name in all_scheduled_instances:
                inst_course_base_name = inst_course_name.split(' (')[0].strip()
                key = (inst_term, inst_course_base_name, inst_teacher_name)
                course_offering_num_periods_scheduled[key] += 1

            for offering_key, num_scheduled_periods in course_offering_num_periods_scheduled.items():
                term_off, base_name_off, teacher_off = offering_key
                course_details = self._get_course_details_by_name(base_name_off)

                if course_details:
                    credits = course_details.get('credits')
                    actual_minutes_per_week = num_scheduled_periods * period_duration
                    deviation_in_periods = 0 # How many "period equivalents" off target

                    if credits == 1:
                        target_minutes = 90
                        deviation_in_periods = abs(actual_minutes_per_week - target_minutes) / period_duration
                    elif credits == 5:
                        target_minutes = 450
                        deviation_in_periods = abs(actual_minutes_per_week - target_minutes) / period_duration
                    elif credits == 3:
                        min_target_minutes = 180
                        max_target_minutes = 270
                        if actual_minutes_per_week < min_target_minutes:
                            deviation_in_periods = (min_target_minutes - actual_minutes_per_week) / period_duration
                        elif actual_minutes_per_week > max_target_minutes:
                            deviation_in_periods = (actual_minutes_per_week - max_target_minutes) / period_duration
                    
                    if deviation_in_periods > 0.01: # Using a small epsilon to avoid floating point issues for near-exact matches
                        cost += PENALTY_CREDIT_MINUTES_MISMATCH * deviation_in_periods
                        self._log_message(f"COST (Credit-Minutes): {base_name_off} ({credits}cr, T:{teacher_off}, Term:{term_off}) has {actual_minutes_per_week} min/wk ({num_scheduled_periods} pds). Deviation: {deviation_in_periods:.2f} pds.", "TRACE")
        # --- END: New Penalty for Credit-Minutes Mismatch ---

        return cost

    def get_random_neighbor_schedule(self, current_schedule, items_by_term_for_moves):
        neighbor_schedule = copy.deepcopy(current_schedule)
        num_terms = self.params.get('num_terms', 1)
        num_p_day = self.params.get('num_periods_per_day', 1)
        num_tracks = self.params.get('num_concurrent_tracks_per_period', 1)

        all_slots = []
        for t in range(1, num_terms + 1):
            for d_idx, d_name in enumerate(DAYS_OF_WEEK):
                for p in range(num_p_day):
                    for trk in range(num_tracks):
                        all_slots.append((t, d_name, p, trk))

        if not all_slots: return neighbor_schedule

        move_type = random.choice(["move_class", "swap_classes"])

        occupied_slots_info = []
        for term_idx, term_data in neighbor_schedule.items():
            for day_name, day_slots_data in term_data.items():
                for period_idx, period_tracks_data in enumerate(day_slots_data):
                    for track_idx, slot_item in enumerate(period_tracks_data):
                        if slot_item and slot_item[0]:
                            occupied_slots_info.append((term_idx, day_name, period_idx, track_idx, slot_item[0], slot_item[1]))

        if not occupied_slots_info :
            return neighbor_schedule

        if move_type == "move_class" and occupied_slots_info:
            term1, day1, p1, track1, course_name1, teacher_name1 = random.choice(occupied_slots_info)
            term2, day2, p2, track2 = random.choice(all_slots)

            while (term1, day1, p1, track1) == (term2, day2, p2, track2) and len(all_slots) > 1 :
                 term2, day2, p2, track2 = random.choice(all_slots)
            if (term1, day1, p1, track1) == (term2, day2, p2, track2) : return neighbor_schedule


            target_slot_content = neighbor_schedule[term2][day2][p2][track2]

            neighbor_schedule[term2][day2][p2][track2] = (course_name1, teacher_name1)
            neighbor_schedule[term1][day1][p1][track1] = None

            if target_slot_content and target_slot_content[0]:
                self._log_message(f"SA_MOVE: Moved {course_name1} to T{term2}-{day2}-P{p2+1}-Trk{track2+1}. Displaced {target_slot_content[0]} (if any).", "TRACE")
            else:
                self._log_message(f"SA_MOVE: Moved {course_name1} from T{term1}-{day1}-P{p1+1}-Trk{track1+1} to empty T{term2}-{day2}-P{p2+1}-Trk{track2+1}.", "TRACE")

        elif move_type == "swap_classes" and len(occupied_slots_info) >= 2:
            idx1 = random.randrange(len(occupied_slots_info))
            idx2 = random.randrange(len(occupied_slots_info))
            while idx1 == idx2:
                idx2 = random.randrange(len(occupied_slots_info))

            term1, day1, p1, track1, course_name1, teacher_name1 = occupied_slots_info[idx1]
            term2, day2, p2, track2, course_name2, teacher_name2 = occupied_slots_info[idx2]

            neighbor_schedule[term1][day1][p1][track1] = (course_name2, teacher_name2)
            neighbor_schedule[term2][day2][p2][track2] = (course_name1, teacher_name1)
            self._log_message(f"SA_SWAP: Swapped {course_name1} (T{term1}-{day1}-P{p1+1}-Trk{track1+1}) with {course_name2} (T{term2}-{day2}-P{p2+1}-Trk{track2+1}).", "TRACE")

        return neighbor_schedule

    def generate_initial_complete_schedule(self):
        self._log_message("--- Generating Initial Schedule for SA ---", "INFO")
        num_p_day = self.params.get('num_periods_per_day', 1)
        num_terms = self.params.get('num_terms', 1)
        num_tracks = self.params.get('num_concurrent_tracks_per_period', 1)

        schedule = {t: {d: [[None] * num_tracks for _ in range(num_p_day)] for d in DAYS_OF_WEEK} for t in range(1, num_terms + 1)}

        all_course_instances_to_place = []
        source_data = self.subjects_data if self.params.get('school_type') == 'Elementary' else self.courses_data_master

        items_by_term_for_initial = defaultdict(list)
        for item_data_orig in source_data:
            item_data = copy.deepcopy(item_data_orig)
            if item_data is None : continue
            term_num_item = item_data.get('term_assignment', 1)
            is_elem = self.params.get('school_type') == 'Elementary'
            terms_to_sched_in = list(range(1, num_terms + 1)) if is_elem and num_terms > 1 else [term_num_item]

            for term_actual in terms_to_sched_in:
                if term_actual > num_terms: continue
                periods_to_schedule = item_data.get('periods_per_week_in_active_term', 0)
                if is_elem: periods_to_schedule = item_data.get('periods_per_week',0)

                item_copy_for_map = copy.deepcopy(item_data)
                item_copy_for_map['periods_to_schedule_this_week'] = periods_to_schedule
                item_copy_for_map['term_assignment'] = term_actual
                items_by_term_for_initial[term_actual].append(item_copy_for_map)

                for _ in range(periods_to_schedule):
                    all_course_instances_to_place.append({'data': item_data, 'term': term_actual, 'assigned_teacher': None})

        random.shuffle(all_course_instances_to_place)

        available_slots = []
        for t in range(1, num_terms + 1):
            for day_name in DAYS_OF_WEEK:
                for p_idx in range(num_p_day):
                    for track_idx in range(num_tracks):
                        available_slots.append({'term': t, 'day': day_name, 'period': p_idx, 'track': track_idx})
        random.shuffle(available_slots)

        placed_count = 0
        for course_instance in all_course_instances_to_place:
            course_data = course_instance['data']
            target_term = course_instance['term']
            assigned_teacher_name = course_data.get('assigned_teacher_name')
            if not assigned_teacher_name:
                potential_teachers = [t['name'] for t in self.teachers_data if self._is_teacher_qualified(t, course_data.get('subject_area'))]
                if potential_teachers:
                    assigned_teacher_name = random.choice(potential_teachers)
                else:
                    assigned_teacher_name = "UNQUALIFIED_PLACEHOLDER"
                    self._log_message(f"INITIAL_SCHED: No qualified teacher for {course_data['name']}. Using placeholder.", "WARN")

            course_instance['assigned_teacher'] = assigned_teacher_name
            assigned_by_constraint = False
            if course_data.get('parsed_constraints'):
                for constr in course_data['parsed_constraints']:
                    if constr['type'] == 'ASSIGN' and constr['day'] and constr['period'] is not None:
                        assign_day, assign_period = constr['day'], constr['period']
                        if target_term == course_data.get('term_assignment', target_term):
                            for trk_idx_assign in range(num_tracks):
                                if schedule[target_term][assign_day][assign_period][trk_idx_assign] is None:
                                    schedule[target_term][assign_day][assign_period][trk_idx_assign] = (course_data['name'], assigned_teacher_name)
                                    assigned_by_constraint = True
                                    placed_count += 1
                                    try:
                                        available_slots.remove({'term': target_term, 'day': assign_day, 'period': assign_period, 'track': trk_idx_assign})
                                    except ValueError: pass
                                    break
                        if assigned_by_constraint: break

            if assigned_by_constraint: continue

            slot_found_for_course = False
            for slot_candidate in available_slots:
                if slot_candidate['term'] == target_term:
                    teacher_obj = self._get_teacher_object_by_name(assigned_teacher_name)
                    teacher_available = False
                    if teacher_obj:
                         teacher_available = teacher_obj.get('availability', {}).get(slot_candidate['day'], {}).get(slot_candidate['period'], False)
                    elif assigned_teacher_name == "UNQUALIFIED_PLACEHOLDER":
                        teacher_available = True

                    constraint_ok = True
                    if course_data.get('parsed_constraints'):
                        for constr in course_data['parsed_constraints']:
                            if constr['type'] == 'NOT':
                                if (constr['day'] is None or constr['day'] == slot_candidate['day']) and \
                                   constr['period'] == slot_candidate['period']:
                                    constraint_ok = False
                                    break

                    if schedule[slot_candidate['term']][slot_candidate['day']][slot_candidate['period']][slot_candidate['track']] is None and teacher_available and constraint_ok:
                        schedule[slot_candidate['term']][slot_candidate['day']][slot_candidate['period']][slot_candidate['track']] = (course_data['name'], assigned_teacher_name)
                        available_slots.remove(slot_candidate)
                        placed_count += 1
                        slot_found_for_course = True
                        break
            if not slot_found_for_course:
                self._log_message(f"INITIAL_SCHED: Could not find suitable slot for an instance of {course_data['name']} in Term {target_term} (Teacher: {assigned_teacher_name}). Will be unplaced.", "WARN")


        unplaced_count = len(all_course_instances_to_place) - placed_count
        self._log_message(f"Initial schedule: Placed {placed_count} instances, {unplaced_count} unplaced (will be penalized).", "INFO")

        return schedule, items_by_term_for_initial

    def generate_schedule_with_simulated_annealing(self):
        self._log_message("--- Starting Simulated Annealing Scheduler ---", "INFO")

        initial_schedule, items_by_term_map = self.generate_initial_complete_schedule()
        if initial_schedule is None or not items_by_term_map:
            self._log_message("Failed to generate a valid initial schedule or course term map.", "ERROR")
            return None, [], False, {'cost': float('inf')}

        current_schedule = copy.deepcopy(initial_schedule)
        current_cost = self.calculate_schedule_cost(current_schedule, items_by_term_map)

        best_schedule = copy.deepcopy(current_schedule)
        best_cost = current_cost

        self._log_message(f"SA: Initial Cost = {current_cost}", "INFO")

        temperature = SA_INITIAL_TEMPERATURE
        total_iterations = 0
        run_log_sa = [f"SA Initial Cost: {current_cost}"]

        while temperature > SA_MIN_TEMPERATURE and total_iterations < SA_MAX_TOTAL_ITERATIONS:
            for i in range(SA_ITERATIONS_PER_TEMPERATURE):
                if total_iterations >= SA_MAX_TOTAL_ITERATIONS: break
                total_iterations += 1

                neighbor_schedule = self.get_random_neighbor_schedule(current_schedule, items_by_term_map)
                neighbor_cost = self.calculate_schedule_cost(neighbor_schedule, items_by_term_map)
                cost_delta = neighbor_cost - current_cost

                if cost_delta < 0:
                    current_schedule = neighbor_schedule
                    current_cost = neighbor_cost
                    if current_cost < best_cost:
                        best_schedule = copy.deepcopy(current_schedule)
                        best_cost = current_cost
                        run_log_sa.append(f"Iter {total_iterations}, T={temperature:.2f}: New best! Cost = {best_cost}")
                else:
                    acceptance_probability = math.exp(-cost_delta / temperature) if temperature > 0 else 0
                    if random.random() < acceptance_probability:
                        current_schedule = neighbor_schedule
                        current_cost = neighbor_cost
            temperature *= SA_COOLING_RATE
            if total_iterations % (SA_ITERATIONS_PER_TEMPERATURE * 10) == 0 :
                 self._log_message(f"SA Iter: {total_iterations}, Temp: {temperature:.2f}, Current Cost: {current_cost}, Best Cost: {best_cost}", "DEBUG")
                 run_log_sa.append(f"SA Iter: {total_iterations}, Temp: {temperature:.2f}, Current Cost: {current_cost}, Best Cost: {best_cost}")

        self._log_message(f"--- SA Finished. Best cost: {best_cost} after {total_iterations} iterations ---", "INFO")
        run_log_sa.append(f"SA Final Best Cost: {best_cost}")

        is_successful = best_cost == 0
        if not is_successful and best_cost < PENALTY_UNPLACED_COURSE_PERIOD:
            self._log_message(f"SA Result: Cost {best_cost} is non-zero but low, considered acceptable.", "INFO")
            is_successful = True

        metrics = {'cost': best_cost, 'iterations': total_iterations}

        return best_schedule, run_log_sa, is_successful, metrics

    def _calculate_period_times_for_display(self):
        num_p, p_dur, b_dur = self.params.get('num_periods_per_day',0), self.params.get('period_duration_minutes',0), self.params.get('break_between_classes_minutes',0)
        s_start_t, l_start_t, l_end_t = self.params.get('school_start_time'), self.params.get('lunch_start_time'), self.params.get('lunch_end_time')
        if not all([isinstance(num_p, int) and num_p > 0, isinstance(p_dur, int) and p_dur > 0, s_start_t, l_start_t, l_end_t]): return [f"P{i+1}" for i in range(num_p if isinstance(num_p, int) and num_p > 0 else 1)]
        s_start_m, l_start_m, l_end_m = time_to_minutes(s_start_t), time_to_minutes(l_start_t), time_to_minutes(l_end_t)
        times, current_m = [], s_start_m
        for i in range(num_p):
            if l_start_m <= current_m < l_end_m: current_m = l_end_m
            period_start_candidate, period_end_candidate = current_m, current_m + p_dur
            
            if period_start_candidate < l_start_m and period_end_candidate > l_start_m:
                current_m = l_end_m
                period_start_candidate, period_end_candidate = current_m, current_m + p_dur
            elif l_start_m <= period_start_candidate < l_end_m:
                 current_m = l_end_m
                 period_start_candidate, period_end_candidate = current_m, current_m + p_dur

            times.append(f"{format_time_from_minutes(period_start_candidate)}-{format_time_from_minutes(period_end_candidate)}")
            current_m = period_end_candidate
            if i < num_p -1 : current_m += b_dur
        return times

    def display_schedules_console(self):
        if not self.generated_schedules_details: print("No schedules generated to display."); return
        period_times = self._calculate_period_times_for_display(); num_p = self.params.get('num_periods_per_day',0); num_tracks = self.params.get('num_concurrent_tracks_per_period', 1)
        if not isinstance(num_p, int) or num_p <= 0: num_p = 1
        for sched_detail in self.generated_schedules_details:
            s_id, schedule, log = sched_detail['id'], sched_detail['schedule'], sched_detail.get('log_summary', sched_detail.get('log', []))
            print(f"\n\n--- TIMETABLE - SCHEDULE ID: {s_id} ---")

            if 'metrics' in sched_detail and sched_detail['metrics']:
                metrics = sched_detail['metrics']
                print(f"  (Metrics: Final Cost: {metrics.get('cost', 'N/A')}, Iterations: {metrics.get('iterations', 'N/A')})")
                if not sched_detail.get('is_successful', True) :
                     print(f"  (SA attempt did not reach ideal cost. Cost indicates constraint violations.)")

            log_key = f'view_log_sched_{s_id}_{random.randint(1000,9999)}'
            if self.get_input_with_default(log_key, f"View generation log for Sched {s_id}?", str, lambda x:x.lower() in ['yes','no'], choices=['yes','no']).lower()=='yes':
                print(f"\n--- Log for Sched ID: {s_id} ---"); [print(entry) for entry in log]; print("--- End Log ---")

            if not schedule:
                print("  ERROR: No schedule data available for this entry.")
                continue

            for term_idx, term_data in schedule.items():
                print(f"\n--- Term {term_idx} (Sched ID: {s_id}) ---"); header = ["Period/Time"] + DAYS_OF_WEEK; table_data = [header]
                for p_idx in range(num_p):
                    p_label = f"P{p_idx+1}";
                    if p_idx < len(period_times) and not period_times[p_idx].startswith("P"): p_label += f"\n{period_times[p_idx]}"
                    row_content = [p_label]
                    for day_name in DAYS_OF_WEEK:
                        cell_entries = []
                        for track_idx in range(num_tracks):
                            day_schedule = term_data.get(day_name, [])
                            period_schedule_for_day = day_schedule[p_idx] if p_idx < len(day_schedule) else []
                            entry = period_schedule_for_day[track_idx] if track_idx < len(period_schedule_for_day) else None

                            trk_lab = f"[Trk{track_idx+1}] " if num_tracks > 1 else ""
                            if entry and entry[0]: cell_entries.append(f"{trk_lab}{entry[0][:25]}\n({entry[1][:10] if entry[1] else 'No T.'})")
                            else: cell_entries.append(f"{trk_lab}---")
                        has_content = any(not e.endswith("---") for e in cell_entries)
                        if num_tracks > 1 and has_content : row_content.append("\n---\n".join(cell_entries))
                        elif num_tracks > 1 and not has_content: row_content.append(cell_entries[0])
                        else: row_content.append(cell_entries[0])
                    table_data.append(row_content)
                try:
                    from tabulate import tabulate; print(tabulate(table_data, headers="firstrow", tablefmt="grid"))
                except ImportError:
                    print("`tabulate` not found. Basic table:")
                    for r_idx_b, r_val_b in enumerate(table_data):
                        max_lines_in_row_b = max(len(str(c_val_b).split('\n')) for c_val_b in r_val_b)
                        for line_n_b in range(max_lines_in_row_b): print(" | ".join( (str(c_val_b).split('\n')[line_n_b] if line_n_b < len(str(c_val_b).split('\n')) else "").ljust(30) for c_val_b in r_val_b) )
                        if r_idx_b == 0: print("-" * (30 * len(r_val_b) + (len(r_val_b)-1)*3 ) )

    def export_schedules_pdf(self):
        if not self.generated_schedules_details: print("No schedules to export."); return
        safe_name = "".join(x if x.isalnum() else "_" for x in self.params.get('school_name', 'School')); today = datetime.date.today().strftime("%Y-%m-%d")
        num_s = len(self.generated_schedules_details); base_fn = f"{safe_name}_Schedules_{today}"; final_fn = f"{base_fn}.pdf"
        print(f"\n--- Exporting {num_s} Schedule(s) to PDF: {final_fn} ---")
        try:
            doc = SimpleDocTemplate(final_fn, pagesize=landscape(letter)); styles = getSampleStyleSheet(); story = []
            period_times_pdf = self._calculate_period_times_for_display(); num_p = self.params.get('num_periods_per_day',0); num_tracks = self.params.get('num_concurrent_tracks_per_period', 1)
            if not isinstance(num_p, int) or num_p <= 0: num_p = 1
            for i, sched_detail in enumerate(self.generated_schedules_details):
                s_id, schedule = sched_detail['id'], sched_detail['schedule']

                story.append(Paragraph(f"Master Schedule - {self.params.get('school_name', 'N/A')} (ID: {s_id})", styles['h1']))
                if 'metrics' in sched_detail and sched_detail['metrics']:
                    metrics = sched_detail['metrics']
                    story.append(Paragraph(f"<i>(Metrics: Final Cost: {metrics.get('cost', 'N/A')}, Iterations: {metrics.get('iterations', 'N/A')})</i>", styles['Normal']))
                    if not sched_detail.get('is_successful', True):
                         story.append(Paragraph(f"<i>(Note: SA attempt did not reach ideal cost, indicating potential constraint violations.)</i>", styles['Normal']))

                story.append(Paragraph(f"Generated: {today}", styles['Normal'])); story.append(Spacer(1, 0.2*72))

                if not schedule:
                    story.append(Paragraph("ERROR: No schedule data available for this entry.", styles['h2']))
                    if i < num_s - 1: story.append(PageBreak())
                    continue

                for term_idx, term_data in schedule.items():
                    story.append(Paragraph(f"Term {term_idx}", styles['h2'])); story.append(Spacer(1, 0.1*72))
                    pdf_data = [[Paragraph("<b>Period/Time</b>", styles['Normal'])] + [Paragraph(f"<b>{d}</b>", styles['Normal']) for d in DAYS_OF_WEEK]]
                    for p_idx in range(num_p):
                        p_label_pdf = f"<b>P{p_idx+1}</b>"
                        if p_idx < len(period_times_pdf) and not period_times_pdf[p_idx].startswith("P"): p_label_pdf += f"<br/>{period_times_pdf[p_idx]}"
                        row_pdf = [Paragraph(p_label_pdf, styles['Normal'])]
                        for day_name in DAYS_OF_WEEK:
                            cell_paras = []
                            for track_idx in range(num_tracks):
                                day_schedule_pdf = term_data.get(day_name, [])
                                period_schedule_for_day_pdf = day_schedule_pdf[p_idx] if p_idx < len(day_schedule_pdf) else []
                                entry = period_schedule_for_day_pdf[track_idx] if track_idx < len(period_schedule_for_day_pdf) else None

                                trk_lab_pdf = f"<i>Trk{track_idx+1}:</i> " if num_tracks > 1 else ""
                                if entry and entry[0]: cell_paras.append(Paragraph(f"{trk_lab_pdf}{entry[0]}<br/>({entry[1] if entry[1] else 'No T.'})", styles['Normal']))
                                else: cell_paras.append(Paragraph(f"{trk_lab_pdf}---", styles['Normal']))
                            row_pdf.append(cell_paras)
                        pdf_data.append(row_pdf)
                    pw, _ = landscape(letter); aw = pw - 1.5*72; col_w = [aw*0.15] + [(aw*0.85)/len(DAYS_OF_WEEK)]*len(DAYS_OF_WEEK)
                    table = Table(pdf_data, colWidths=col_w, repeatRows=1)
                    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor("#CCCCCC")),('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('FONTNAME',(0,0),(-1,-1),'Helvetica'),('FONTSIZE',(0,0),(-1,-1),7),('GRID',(0,0),(-1,-1),0.5,colors.black),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
                    story.append(table); story.append(Spacer(1, 0.2*72))
                if i < num_s - 1: story.append(PageBreak())
            doc.build(story); print(f"Schedule(s) exported to {final_fn}")
        except ImportError: print("`reportlab` not found. PDF export failed.")
        except Exception as e: print(f"PDF export error: {e}"); traceback.print_exc()

    def run_once(self):
        print("\n--- Starting New Schedule Generation Run (Simulated Annealing) ---")
        self.current_run_log = []
        self.display_info_needed()
        self.get_school_type()
        self.get_operational_parameters()
        self.get_course_structure_model()
        self.get_period_structure_details()

        self.get_teachers_data()
        if not self.teachers_data:
            print("No teachers defined. Cannot schedule.");
            self._log_message("CRITICAL: No teachers defined. Exiting.", "ERROR")
            return

        critically_low_teacher_availability = True
        if self.teachers_data:
            num_p_day_check = self.params.get('num_periods_per_day', 1)
            if not isinstance(num_p_day_check, int) or num_p_day_check <= 0: num_p_day_check = 1
            for t_check_avail in self.teachers_data:
                avail_slots = 0
                for day_c in DAYS_OF_WEEK:
                    for p_c in range(num_p_day_check):
                        if t_check_avail.get('availability',{}).get(day_c,{}).get(p_c,False): avail_slots += 1
                if avail_slots > MIN_PREP_BLOCKS_PER_WEEK: critically_low_teacher_availability = False; break
        if critically_low_teacher_availability and self.teachers_data:
            print("CRITICAL OVERALL WARNING: No teachers have sufficient availability for teaching + prep.")
            self._log_message("CRITICAL: No teachers have sufficient availability for teaching + prep.", "ERROR")
        elif self.teachers_data:
            self._log_message("INFO: At least one teacher has sufficient availability.", "INFO")

        if self.params.get('school_type') == 'Elementary':
            self.get_elementary_subjects()
            if not self.subjects_data:
                print("No subjects defined. Cannot generate a schedule.");
                self._log_message("CRITICAL: No subjects defined. Exiting.", "ERROR")
                return
        elif self.params.get('school_type') == 'High School':
            self.get_high_school_courses()
            self.get_program_specific_constraints()
            self.get_general_constraints()
            if not self.courses_data_master:
                print("No courses defined. Cannot generate a schedule.");
                self._log_message("CRITICAL: No courses defined. Exiting.", "ERROR")
                return
        else:
            print("School type not set. Cannot proceed.");
            self._log_message("CRITICAL: School type not set. Exiting.", "ERROR")
            return

        print(f"\n--- Attempting Schedule Generation with Simulated Annealing ---")
        self._log_message(f"SA Parameters: Init_T={SA_INITIAL_TEMPERATURE}, Cool={SA_COOLING_RATE}, Min_T={SA_MIN_TEMPERATURE}, Iter/T={SA_ITERATIONS_PER_TEMPERATURE}, MaxIter={SA_MAX_TOTAL_ITERATIONS}", "DEBUG")

        final_schedule, sa_log, is_successful, metrics = self.generate_schedule_with_simulated_annealing()

        self.current_run_log.extend(sa_log)
        self.generated_schedules_details = []

        if final_schedule:
            self.generated_schedules_details.append({
                'id': "SA_Result_1",
                'schedule': final_schedule,
                'log_summary': sa_log,
                'is_successful': is_successful,
                'metrics': metrics
            })
            if is_successful:
                print(f"\nSUCCESS: Simulated Annealing found a schedule with acceptable cost: {metrics.get('cost', 'N/A')}.")
            else:
                print(f"\nINFO: Simulated Annealing completed. Best schedule cost: {metrics.get('cost', 'N/A')}. This may indicate constraint violations.")
        else:
            print(f"\nERROR: Simulated Annealing could not produce a schedule. Final cost: {metrics.get('cost', 'N/A')}. Review logs for details.")
            self.generated_schedules_details.append({
                'id': "SA_Failed_No_Schedule",
                'schedule': None,
                'log_summary': sa_log,
                'is_successful': False,
                'metrics': metrics
            })

        if self.generated_schedules_details and self.generated_schedules_details[0]['schedule']:
            self.display_schedules_console()
            export_key = f'export_pdf_choice_{random.randint(1000,9999)}'
            if self.get_input_with_default(export_key, "\nExport generated schedule(s) to PDF?", str, lambda x: x.lower() in ['yes','no'], choices=['yes','no']).lower() == 'yes':
                self.export_schedules_pdf()
        elif not (self.generated_schedules_details and self.generated_schedules_details[0]['schedule']):
             print("No valid schedule data was generated to display or export.")

        log_main_key = f'view_main_run_log_{random.randint(1000,9999)}'
        if self.get_input_with_default(log_main_key, "View main operational log for this run?", str, lambda x:x.lower() in ['yes','no'], choices=['yes','no']).lower()=='yes':
            print("\n--- Main Operational Log ---");
            [print(msg) for msg in self.current_run_log];
            print("--- End Main Log ---")

    def run(self):
        print("Welcome to the School Scheduler!")
        try:
            if os.path.exists("scheduler_session_cache.tmp"):
                with open("scheduler_session_cache.tmp", "r") as f: loaded_cache_raw = json.load(f)
                self.session_cache = loaded_cache_raw

                param_keys_from_cache = {
                    'num_periods_per_day': int, 'min_instructional_hours': int, 'num_terms': int,
                    'weeks_per_term': int, 'instructional_days': int, 'num_instructional_weeks': int,
                    'break_between_classes_minutes': int, 'num_concurrent_tracks_per_period': int,
                    'total_annual_instructional_hours': float, 'school_type': str, 'scheduling_model': str,
                    'school_name': str, 'start_date_str': str, 'end_date_str': str, 'non_instructional_days_str': str,
                    'start_time_str': str, 'end_time_str': str, 'lunch_start_time_str': str, 'lunch_end_time_str': str,
                    'multiple_times_same_day_choice': str,
                    'enforce_cree_per_term_choice': str
                    }
                for p_key, expected_type in param_keys_from_cache.items():
                    if p_key in self.session_cache:
                        try:
                            if p_key == 'multiple_times_same_day_choice': self.params['multiple_times_same_day'] = (self.session_cache[p_key].lower() == 'yes')
                            elif p_key == 'enforce_cree_per_term_choice': self.params['enforce_cree_per_term'] = (self.session_cache.get(p_key,'no').lower() == 'yes')
                            elif self.session_cache[p_key] is not None: self.params[p_key] = expected_type(self.session_cache[p_key])
                        except (ValueError, TypeError) as e:
                            self._log_message(f"Cache Load Error: param '{p_key}' val '{self.session_cache.get(p_key)}' to {expected_type.__name__}: {e}. Using default.", "WARN")
                            if p_key == 'num_periods_per_day': self.params[p_key] = 1
                            elif p_key == 'num_terms': self.params[p_key] = 1

                synced_credits_db = copy.deepcopy(HIGH_SCHOOL_COURSE_CREDITS_TEMPLATE)
                cached_db_data = self.session_cache.get('high_school_credits_db')
                if isinstance(cached_db_data, dict):
                    for course_name_cache, credits_cache in cached_db_data.items():
                        synced_credits_db[course_name_cache] = credits_cache
                    self._log_message("Successfully synced 'high_school_credits_db' with cached data.", "DEBUG")
                elif cached_db_data is not None:
                     self._log_message("Cached 'high_school_credits_db' is not a dict. Using script template only.", "WARN")

                self.high_school_credits_db = synced_credits_db
                self.session_cache['high_school_credits_db'] = copy.deepcopy(self.high_school_credits_db)

                if 'teachers_data' in self.session_cache and isinstance(self.session_cache['teachers_data'], list):
                    num_p_day_at_load = self.params.get('num_periods_per_day', 1)
                    if not isinstance(num_p_day_at_load, int):
                        try: num_p_day_at_load = int(num_p_day_at_load)
                        except (ValueError, TypeError): num_p_day_at_load = 1
                    if num_p_day_at_load <= 0: num_p_day_at_load = 1

                    re_parsed_teachers = []
                    for teacher_entry in self.session_cache['teachers_data']:
                        updated_teacher_entry = copy.deepcopy(teacher_entry)
                        raw_avail_str = updated_teacher_entry.get('raw_availability_str', "")
                        updated_teacher_entry['availability'] = parse_teacher_availability(raw_avail_str, num_p_day_at_load)
                        re_parsed_teachers.append(updated_teacher_entry)
                    self.session_cache['teachers_data'] = re_parsed_teachers

                self._log_message(f"Loaded previous session. School type: {self.params.get('school_type', 'N/A')}, Num_periods: {self.params.get('num_periods_per_day', 'N/A')}.", "INFO")
                print("INFO: Loaded previous session data and synced course credits.")
            else:
                self.session_cache = {}
                self.high_school_credits_db = copy.deepcopy(HIGH_SCHOOL_COURSE_CREDITS_TEMPLATE)
                print("INFO: No previous session cache file found. Starting fresh.")
        except json.JSONDecodeError as e:
            self.session_cache = {}; self.high_school_credits_db = copy.deepcopy(HIGH_SCHOOL_COURSE_CREDITS_TEMPLATE)
            print(f"WARN: Could not decode session cache ({e}). Starting fresh.")
        except Exception as e_load:
            self.session_cache = {}; self.high_school_credits_db = copy.deepcopy(HIGH_SCHOOL_COURSE_CREDITS_TEMPLATE)
            print(f"WARN: Error loading session cache ({type(e_load).__name__}: {e_load}). Starting fresh."); traceback.print_exc()

        while True:
            current_run_cache_backup = copy.deepcopy(self.session_cache)
            try:
                self.run_once()
                try:
                    self.session_cache['high_school_credits_db'] = copy.deepcopy(self.high_school_credits_db)
                    if self.params.get('school_type') == 'High School':
                        self.session_cache['courses_data'] = copy.deepcopy(self.courses_data_master)
                        if hasattr(self, 'cohort_constraints'):
                             self.session_cache['cohort_constraints_list'] = copy.deepcopy(self.cohort_constraints)
                    elif self.params.get('school_type') == 'Elementary':
                         self.session_cache['subjects_data'] = copy.deepcopy(self.subjects_data)
                    
                    if hasattr(self, 'teachers_data'):
                         self.session_cache['teachers_data'] = copy.deepcopy(self.teachers_data)

                    if 'enforce_cree_per_term' in self.params:
                        self.session_cache['enforce_cree_per_term_choice'] = 'yes' if self.params['enforce_cree_per_term'] else 'no'


                    with open("scheduler_session_cache.tmp", "w") as f:
                        serializable_cache = {}
                        for k_c, v_c_item in self.session_cache.items():
                            try:
                                if isinstance(v_c_item, (datetime.date, datetime.time, datetime.datetime)):
                                    serializable_cache[k_c] = v_c_item.isoformat()
                                else:
                                    json.dumps({k_c: v_c_item})
                                    serializable_cache[k_c] = v_c_item
                            except TypeError:
                                self._log_message(f"Cache Save: Skipping non-serializable key '{k_c}' type {type(v_c_item)}", "WARN")
                        json.dump(serializable_cache, f, indent=2)
                    print("INFO: Current input parameters saved to session cache.")
                except Exception as e_cs: print(f"WARNING: Could not save session cache: {e_cs}"); traceback.print_exc()
            except KeyboardInterrupt: print("\n--- Script interrupted. Exiting. ---"); break
            except Exception as e_run:
                print(f"\n!!! UNEXPECTED ERROR !!!\nType: {type(e_run).__name__}\nMessage: {e_run}"); traceback.print_exc()
                print("Attempting to restore cache to state before this run."); self.session_cache = current_run_cache_backup

            run_again_key_main = f'run_again_main_{random.randint(1000,9999)}'
            if self.get_input_with_default(run_again_key_main, "\nMake changes and try again?", str, lambda x: x.lower() in ['yes', 'no'], choices=['yes','no']).lower() != 'yes':
                print("INFO: Session cache 'scheduler_session_cache.tmp' retained."); break
            self.generated_schedules_details = []
            if 'hs_credit_db_modified_once' in self.session_cache:
                del self.session_cache['hs_credit_db_modified_once']

            print("\n" + "="*25 + " RESTARTING WITH MODIFICATIONS " + "="*25 + "\n")
        print("\n--- Script Finished ---")

if __name__ == "__main__":
    scheduler_app = SchoolScheduler()
    scheduler_app.run()
