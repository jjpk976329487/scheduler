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
MAX_SCHEDULE_GENERATION_ATTEMPTS = 20
MAX_DISTINCT_SCHEDULES_TO_GENERATE = 10 # Can be adjusted by user
MIN_PREP_BLOCKS_PER_WEEK = 2
MIN_ACCEPTABLE_SCHEDULE_COMPLETION_RATE = 0.75 # Proportion of *defined* course periods
GRADES_REQUIRING_FULL_SCHEDULE = [10, 11, 12]
PERIODS_PER_TYPICAL_OPTION_BLOCK = 5 # Default size for option blocks if not dynamically determined


QUALIFIABLE_SUBJECTS = [
    "Math", "Science", "Social Studies", "English", "French",
    "PE", "Cree", "CTS", "Other"
]

CORE_SUBJECTS_HS = ["English", "Math", "Science", "Social Studies"]

HIGH_SCHOOL_COURSE_CREDITS_TEMPLATE = {
    # Grade 10
    "English 10-1": 5, "English 10-2": 5, "English 10-4": 5,
    "Social Studies 10-1": 5, "Social Studies 10-2": 5, "Social Studies 10-4": 5,
    "Math 10C": 5, "Math 10-4": 5,
    "Science 10": 5, "Science 14": 5, "Science 10-4": 5,
    "Physical Education 10": 5, # Can also be 3, but 5 is common
    "CALM 20": 3, # Often taken in Grade 10 or 11
    "Art 10": 3, "Drama 10": 3, "Music 10": 3, "French 10": 5,
    "Construction Technologies 10": 5, # Example CTS

    # Grade 11
    "English 20-1": 5, "English 20-2": 5, "English 20-4": 5,
    "Social Studies 20-1": 5, "Social Studies 20-2": 5, "Social Studies 20-4": 5,
    "Math 20-1": 5, "Math 20-2": 5, "Math 20-4": 5,
    "Biology 20": 5, "Chemistry 20": 5, "Physics 20": 5, "Science 20": 5,
    "Science 24": 5, "Science 20-4": 5,
    "Art 20": 3, "Drama 20": 3, "Music 20": 3, "French 20": 5,
    # Add more Grade 11 options/CTS as needed

    # Grade 12
    "English 30-1": 5, "English 30-2": 5, "English 30-4": 5,
    "Social Studies 30-1": 5, "Social Studies 30-2": 5,
    "Math 30-1": 5, "Math 30-2": 5, "Math 30-4": 5,
    "Biology 30": 5, "Chemistry 30": 5, "Physics 30": 5, "Science 30": 5,
    "Art 30": 3, "Drama 30": 3, "Music 30": 3, "French 30": 5,
    # Add more Grade 12 options/CTS as needed
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
    if not isinstance(num_periods, int) or num_periods <= 0: num_periods = 1 # Safety
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
        self.courses_data = []
        self.subjects_data = []
        self.cohort_constraints = []
        self.current_run_log = []
        self.high_school_credits_db = copy.deepcopy(HIGH_SCHOOL_COURSE_CREDITS_TEMPLATE)

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
        print(f"  - (The system will aim to schedule at least {MIN_ACCEPTABLE_SCHEDULE_COMPLETION_RATE*100:.0f}% of requested course periods per term)")
        print("  **Elementary:** Subjects, Periods/week, Constraints (e.g., 'Math NOT P1')")
        print("  **High School:** Courses, Credits, Grade Level (10, 11, 12, or Mixed), Subject Area, Term, Constraints, Cohort Clashes")
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
        if not isinstance(num_p_day, int) or num_p_day <= 0: num_p_day = 1
        p_dur_min = self.params.get('period_duration_minutes', 1)
        if not isinstance(p_dur_min, int) or p_dur_min <= 0: p_dur_min = 60
        
        # weeks_course_dur depends on the scheduling model for calculating periods per week.
        # If full year, it's total weeks. If semester/quarterly, it's weeks per term.
        weeks_course_dur = self.params.get('weeks_per_term', 18) # Default to a semester length if not set
        if self.params.get('scheduling_model') == "Full Year":
            weeks_course_dur = self.params.get('num_instructional_weeks', 36) # Use full year weeks
        if not isinstance(weeks_course_dur, int) or weeks_course_dur <= 0:
            weeks_course_dur = 18 # Fallback

        self._log_message(f"Suggestion engine using: num_terms={num_terms}, p_dur_min={p_dur_min}, weeks_course_dur (for p/wk calc)={weeks_course_dur}", "DEBUG")


        # --- Pass 1: Suggest Core Courses & Key Electives/Alternatives ---
        # These are suggested primarily for the *first available term* or a sensible default term.
        # The option slot filler (Pass 2) will handle filling remaining slots in all terms.
        default_term_for_explicit_suggestions = 1

        explicit_suggestions_data = [
            # Grade 10
            ("English 10-1", "English", 10), ("Social Studies 10-1", "Social Studies", 10),
            ("Math 10C", "Math", 10), ("Science 10", "Science", 10),
            ("CALM 20", "Other", 10), # Often taken in G10 or G11
            ("Science 14", "Science", 10),
            ("English 10-4", "English", 10), ("Math 10-4", "Math", 10),
            ("Social Studies 10-4", "Social Studies", 10), ("Science 10-4", "Science", 10),
            ("Physical Education 10", "PE", 10),

            # Grade 11
            ("English 20-1", "English", 11), ("Social Studies 20-1", "Social Studies", 11),
            ("Math 20-1", "Math", 11),
            ("Biology 20", "Science", 11), ("Chemistry 20", "Science", 11), 
            ("Science 24", "Science", 11),
            ("English 20-4", "English", 11), ("Math 20-4", "Math", 11),
            ("Social Studies 20-4", "Social Studies", 11), ("Science 20-4", "Science", 11),
            # CALM 20 could also be suggested for G11 if desired, or user can change grade

            # Grade 12
            ("English 30-1", "English", 12), ("Social Studies 30-1", "Social Studies", 12),
            ("Math 30-1", "Math", 12),
            ("Biology 30", "Science", 12), ("Chemistry 30", "Science", 12), 
            ("English 30-4", "English", 12), ("Math 30-4", "Math", 12),
        ]
        
        # Add Physics as alternatives if Bio/Chem are already taken by a grade or for variety
        # This part is tricky for auto-suggestion as it depends on student pathways.
        # For now, sticking to Bio/Chem as primary science suggestions past Science 10/14/24. User can add Physics.

        for course_name, subject_area, grade_level in explicit_suggestions_data:
            credits = self.high_school_credits_db.get(course_name)
            if credits is None:
                self._log_message(f"INFO: Explicitly suggested course '{course_name}' not in credit DB. Skipping this suggestion.", "INFO")
                continue

            course_mins_total = credits * CREDITS_TO_HOURS_PER_CREDIT * 60
            
            # periods_per_year_total_instances: How many periods the course would take if it ran 1 period/day for its duration
            periods_per_year_total_instances = math.ceil(course_mins_total / p_dur_min) if p_dur_min > 0 else course_mins_total
            
            # periods_per_week_in_active_term: How many periods per week this course needs *during the term(s) it is taught*.
            # weeks_course_dur is already set to weeks_per_term or num_instructional_weeks based on model.
            periods_per_week_active_term = math.ceil(periods_per_year_total_instances / weeks_course_dur) if weeks_course_dur > 0 else periods_per_year_total_instances
            periods_per_week_active_term = max(1, periods_per_week_active_term if periods_per_year_total_instances > 0 else 0)

            term_assignment_for_suggestion = default_term_for_explicit_suggestions
            
            # Ensure CALM is only suggested once if it appears for G10 and potentially G11 in future lists
            if course_name == "CALM 20":
                if any(s['name'] == "CALM 20" for s in suggested_courses_all_grades):
                    continue # Already suggested CALM 20 (likely for G10)

            is_already_suggested = any(
                sugg['name'] == course_name and
                sugg['grade_level'] == grade_level and
                sugg['term_assignment'] == term_assignment_for_suggestion
                for sugg in suggested_courses_all_grades
            )
            if is_already_suggested:
                self._log_message(f"DEBUG: Course '{course_name}' Gr {grade_level} Term {term_assignment_for_suggestion} already in suggestion list. Skipping duplicate.", "TRACE")
                continue

            suggested_courses_all_grades.append({
                'name': course_name, 'credits': credits, 'grade_level': grade_level,
                'subject_area': subject_area, 'term_assignment': term_assignment_for_suggestion,
                'assigned_teacher_name': None,
                'periods_per_year_total_instances': periods_per_year_total_instances,
                'periods_per_week_in_active_term': periods_per_week_active_term,
                'scheduling_constraints_raw': "", 'parsed_constraints': [], '_is_suggestion': True,
                '_is_one_credit_buffer_item': credits == 1, # Should be false for these suggestions
                '_is_one_credit_buffer_item_from_suggestion': credits == 1
            })
            self._log_message(f"DEBUG: Suggested (Pass 1): {course_name} (Gr{grade_level}, {credits}cr, {periods_per_week_active_term}p/wk in T{term_assignment_for_suggestion})", "TRACE")


        # --- Pass 2: Suggest Option/Elective Slots for Grades Requiring Full Schedule ---
        total_periods_per_week_for_full_schedule = num_p_day * len(DAYS_OF_WEEK)

        # Calculate periods already taken by explicit suggestions for each grade and term
        core_periods_by_grade_term = defaultdict(lambda: defaultdict(int))
        for c_sugg in suggested_courses_all_grades:
            grade = c_sugg.get('grade_level')
            term = c_sugg.get('term_assignment')
            # Only count if it's not an "Option Slot" itself (safeguard if this runs multiple times)
            if grade and term and not c_sugg.get('name', '').lower().startswith("option slot"):
                core_periods_by_grade_term[grade][term] += c_sugg.get('periods_per_week_in_active_term', 0)

        for grade_to_fill in GRADES_REQUIRING_FULL_SCHEDULE:
            for term_num_fill in range(1, num_terms + 1): # Iterate through all terms
                current_explicitly_suggested_periods = core_periods_by_grade_term[grade_to_fill][term_num_fill]
                
                remaining_periods_for_options = total_periods_per_week_for_full_schedule - current_explicitly_suggested_periods
                self._log_message(f"DEBUG: Grade {grade_to_fill}, Term {term_num_fill}: Total slots={total_periods_per_week_for_full_schedule}, Explicitly Suggested={current_explicitly_suggested_periods}, Remaining for options={remaining_periods_for_options}", "TRACE")

                option_slot_counter = 1
                # Possible block sizes for options, prioritized (e.g., 5-period, then 3-period)
                possible_option_block_sizes = [5, 3, 4, 2, 1]

                while remaining_periods_for_options >= 1:
                    periods_for_this_option_slot = 0
                    for block_size in possible_option_block_sizes:
                        if remaining_periods_for_options >= block_size:
                            periods_for_this_option_slot = block_size
                            break
                    
                    if periods_for_this_option_slot == 0: # If remaining is less than smallest block_size (e.g. < 1)
                        periods_for_this_option_slot = remaining_periods_for_options # Take whatever is left

                    if periods_for_this_option_slot <= 0: # Safety break
                        break 
                    
                    option_name = f"Option Slot {option_slot_counter} (Gr {grade_to_fill} Mix)"
                    
                    # Estimate credits for this option slot
                    # weeks_course_dur here should be weeks_per_term because options are typically term-based
                    option_weeks = self.params.get('weeks_per_term', weeks_course_dur) # Use weeks_per_term for options
                    if self.params.get('scheduling_model') == "Full Year": # If full year, option runs all year
                        option_weeks = self.params.get('num_instructional_weeks', weeks_course_dur)


                    option_total_minutes_estimate = periods_for_this_option_slot * option_weeks * p_dur_min
                    option_credits_estimate = math.ceil(option_total_minutes_estimate / (60 * CREDITS_TO_HOURS_PER_CREDIT))
                    option_credits_estimate = max(1, option_credits_estimate)

                    suggested_courses_all_grades.append({
                        'name': option_name,
                        'credits': option_credits_estimate,
                        'grade_level': "Mixed", # Options are typically mixed grade
                        'subject_area': "Other",
                        'term_assignment': term_num_fill,
                        'assigned_teacher_name': None,
                        'periods_per_year_total_instances': periods_for_this_option_slot * option_weeks, # Approx
                        'periods_per_week_in_active_term': periods_for_this_option_slot,
                        'scheduling_constraints_raw': "",
                        'parsed_constraints': [],
                        '_is_suggestion': True,
                        '_is_one_credit_buffer_item': False,
                        '_is_one_credit_buffer_item_from_suggestion': False
                    })
                    self._log_message(f"DEBUG:  Added Option Slot (Pass 2): '{option_name}' for Gr {grade_to_fill} context, Term {term_num_fill} ({periods_for_this_option_slot} p/wk, est. {option_credits_estimate} cr).", "TRACE")
                    
                    remaining_periods_for_options -= periods_for_this_option_slot
                    option_slot_counter += 1
                
                if remaining_periods_for_options > 0 and remaining_periods_for_options < 1 : # tiny fractions
                     self._log_message(f"DEBUG: Grade {grade_to_fill}, Term {term_num_fill}: Tiny fraction {remaining_periods_for_options} p/wk remaining, considered filled.", "TRACE")
                elif remaining_periods_for_options >=1 :
                     self._log_message(f"INFO:  Grade {grade_to_fill}, Term {term_num_fill}: {remaining_periods_for_options} p/wk potentially unfilled by auto-options. User may need to adjust or add more courses.", "INFO")

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
                    else: # Handles None, empty string, or other unexpected string grade_levels
                        grade_counts['Other/Undefined'] += 1
                
                grade_summary_parts = []

                # Define a helper function for sorting grade keys
                def sort_grade_keys(k):
                    if isinstance(k, int):
                        return (0, k)  # Sort integers first, by their value
                    if k == "Mixed":
                        return (1, k)  # Then "Mixed"
                    if k == "Other/Undefined":
                        return (2, k)  # Then "Other/Undefined"
                    # Fallback for any other string keys (should be rare with current logic)
                    return (3, str(k)) 

                for g in sorted(grade_counts.keys(), key=sort_grade_keys): # Sort for consistent order
                    grade_summary_parts.append(f"Grade {g}: {grade_counts[g]}")
                print(f"  Summary: {', '.join(grade_summary_parts)}")
            
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
        
        # Determine weeks_course_dur based on the scheduling model for accurate period/week calculation
        weeks_course_dur = self.params.get('weeks_per_term', 18) # Default for semester/quarter
        if self.params.get('scheduling_model') == "Full Year":
            weeks_course_dur = self.params.get('num_instructional_weeks', 36) # Full year
        if not isinstance(weeks_course_dur, int) or weeks_course_dur <= 0: weeks_course_dur = 18


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
            periods_week_term = math.ceil(periods_year_calc / weeks_course_dur) if weeks_course_dur > 0 else periods_year_calc
            periods_week_term = max(1, periods_week_term if periods_year_calc > 0 else 0)
            print(f"  INFO: Calculated {periods_week_term} periods/week for {course_name} ({credits} credits, based on {weeks_course_dur} weeks duration).")
        else: 
             print(f"  INFO: Using {periods_week_term} periods/week for {course_name} (from suggestion/default).")

        periods_year = defaults.get('periods_per_year_total_instances') 
        if periods_year is None: 
            periods_year = periods_week_term * weeks_course_dur 

        constraints_default = defaults.get('scheduling_constraints_raw', "")
        raw_constr = self.get_input_with_default(f"constraints{prompt_key_suffix}", f"Constraints for {course_name}", str, allow_empty=True, default_value_override=constraints_default)
        parsed_constr = parse_scheduling_constraint(raw_constr, num_p_day)
        assign_slots_count = sum(1 for c in parsed_constr if c.get('type') == 'ASSIGN')
        if assign_slots_count > 0 and assign_slots_count != periods_week_term:
            self._log_message(f"WARN: For {course_name}, ASSIGNed slots ({assign_slots_count}) != calc p/wk ({periods_week_term}). Using ASSIGN count for p/wk.", "WARN")
            periods_week_term = assign_slots_count
            # periods_year might also need adjustment if ASSIGN count dictates periods_week_term
            periods_year = periods_week_term * weeks_course_dur


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
            print("Current HS Course Credits DB:"); [print(f"  {c}: {cr}") for c, cr in sorted(self.high_school_credits_db.items())]
            if self.get_input_with_default('modify_credit_db_choice', "Modify credit DB?", str, lambda x: x.lower() in ['yes','no'], choices=['yes','no']).lower() == 'yes':
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
        self.courses_data = []
        one_credit_courses_buffer = copy.deepcopy(self.session_cache.get('one_credit_courses_buffer', []))
        newly_defined_one_credits_this_round = []
        for item in defined_courses_from_helper:
            if item is None: continue
            if item.get('_is_one_credit_buffer_item'):
                if not any(b['name'] == item['name'] for b in one_credit_courses_buffer + newly_defined_one_credits_this_round):
                    newly_defined_one_credits_this_round.append(item)
            else: self.courses_data.append(item)
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
                
                weeks_course_dur_local = self.params.get('weeks_per_term', 18)
                if self.params.get('scheduling_model') == "Full Year":
                    weeks_course_dur_local = self.params.get('num_instructional_weeks', 36)
                if not isinstance(weeks_course_dur_local, int) or weeks_course_dur_local <= 0: weeks_course_dur_local = 18
                
                if not isinstance(num_p_day_local, int) or num_p_day_local <= 0: num_p_day_local = 1
                if not isinstance(p_dur_min_local, int) or p_dur_min_local <= 0: p_dur_min_local = 1

                block_mins = block_credits * CREDITS_TO_HOURS_PER_CREDIT * 60
                block_periods_year = math.ceil(block_mins / p_dur_min_local) if p_dur_min_local > 0 else block_mins
                block_periods_week = math.ceil(block_periods_year / weeks_course_dur_local) if weeks_course_dur_local > 0 else block_periods_year
                block_periods_week = max(1, block_periods_week if block_periods_year > 0 else 0)
                block_constr_key = f"block_constr_one_credit_{random.randint(1000,9999)}"
                raw_constr_block = self.get_input_with_default(block_constr_key, f"Constraints for block '{block_name}'", str, allow_empty=True)
                parsed_constr_block = parse_scheduling_constraint(raw_constr_block, num_p_day_local)
                assign_slots_block = sum(1 for c in parsed_constr_block if c.get('type') == 'ASSIGN')
                if assign_slots_block > 0 and assign_slots_block != block_periods_week: block_periods_week = assign_slots_block; block_periods_year = block_periods_week * weeks_course_dur_local
                term_assign_block = 1
                block_term_key = f"block_term_one_credit_{random.randint(1000,9999)}"
                if self.params.get('num_terms',1) > 1: term_assign_block = self.get_input_with_default(block_term_key, f"Assign block to term (1-{self.params['num_terms']})", int, lambda x: 1<=x<=self.params['num_terms'])
                self.courses_data.append({'name': block_name + f" (contains: {', '.join(c['name'] for c in block_courses_details)})", 'credits': block_credits, 'grade_level': block_grade_level_final, 'assigned_teacher_name': None, 'subject_area': block_subject_area, 'periods_per_year_total_instances': block_periods_year, 'periods_per_week_in_active_term': block_periods_week, 'scheduling_constraints_raw': raw_constr_block, 'parsed_constraints': parsed_constr_block, 'term_assignment': term_assign_block})
                self._log_message(f"Block '{block_name}' created.", "DEBUG")
                if not one_credit_courses_buffer: self._log_message("All 1-credit courses addressed.", "INFO"); break
        self.session_cache['one_credit_courses_buffer'] = one_credit_courses_buffer
        self.session_cache['courses_data'] = copy.deepcopy(self.courses_data)
        if one_credit_courses_buffer: self._log_message(f"Warning: {len(one_credit_courses_buffer)} 1-credit courses ungrouped.", "WARN")

    def get_general_constraints(self):
        self.cohort_constraints = self._get_list_data('cohort_constraints_list', 'cohort constraint group', 'cohort constraints', self._get_single_cohort_constraint_details)

    def _get_single_cohort_constraint_details(self, defaults=None):
        all_course_names_in_system = [c['name'].split(' (')[0].strip() for c in self.courses_data if c]
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

    def _is_teacher_qualified(self, teacher_obj, subject_area):
        if subject_area == "Other": return True # "Other" subjects can be taught by any teacher
        return subject_area in teacher_obj.get('qualifications', [])

    def _find_qualified_teacher(self, subject_area, day_name, period_idx, teacher_busy_this_term, teacher_teaching_periods_this_week, teacher_max_teaching_this_week, existing_teacher_for_offering=None):
        num_p_day = self.params.get('num_periods_per_day', 1)
        if not isinstance(num_p_day, int) or num_p_day <= 0: num_p_day = 1
        if existing_teacher_for_offering: # If a teacher is already assigned or preferred, try them first
            teacher_obj = next((t for t in self.teachers_data if t['name'] == existing_teacher_for_offering), None)
            if teacher_obj and self._is_teacher_qualified(teacher_obj, subject_area) and \
               teacher_obj.get('availability', {}).get(day_name, {}).get(period_idx, False) and \
               (day_name, period_idx) not in teacher_busy_this_term.get(existing_teacher_for_offering, set()) and \
               teacher_teaching_periods_this_week.get(existing_teacher_for_offering, 0) < teacher_max_teaching_this_week.get(existing_teacher_for_offering, float('-inf')):
                return existing_teacher_for_offering
            return None # Preferred teacher cannot take it
        
        # If no preferred teacher, or preferred teacher is unavailable, find a new one
        shuffled_teachers = random.sample(self.teachers_data, len(self.teachers_data))
        candidate_teachers = []
        for teacher in shuffled_teachers:
            teacher_name = teacher['name']
            if teacher_max_teaching_this_week.get(teacher_name, -1) < 0: continue # Teacher cannot teach due to prep constraints or misconfiguration
            if self._is_teacher_qualified(teacher, subject_area) and \
               teacher.get('availability', {}).get(day_name, {}).get(period_idx, False) and \
               (day_name, period_idx) not in teacher_busy_this_term.get(teacher_name, set()) and \
               teacher_teaching_periods_this_week.get(teacher_name, 0) < teacher_max_teaching_this_week.get(teacher_name, 0):
                candidate_teachers.append(teacher_name)
        return random.choice(candidate_teachers) if candidate_teachers else None

    def _check_cohort_clash_in_slot(self, item_name_to_schedule, term_idx, day_name, period_idx, current_schedule):
        num_tracks = self.params.get('num_concurrent_tracks_per_period', 1)
        base_item_name = item_name_to_schedule.split(' (')[0].strip()
        for track_idx_check in range(num_tracks):
            existing_item_tuple = current_schedule[term_idx][day_name][period_idx][track_idx_check]
            if existing_item_tuple:
                existing_base_name = existing_item_tuple[0].split(' (')[0].strip()
                for clash_group in self.cohort_constraints:
                    if isinstance(clash_group, (list, tuple)) and base_item_name in clash_group and existing_base_name in clash_group:
                        self._log_message(f"COHORT CLASH: '{item_name_to_schedule}' vs '{existing_item_tuple[0]}' in T{term_idx}-{day_name}-P{period_idx+1}", "DEBUG")
                        return True
        return False

    def generate_single_schedule_attempt(self, attempt_seed_modifier=0):
        self.current_run_log.append(f"--- Attempting Schedule Generation (Seed Mod: {attempt_seed_modifier}, Min Prep: {MIN_PREP_BLOCKS_PER_WEEK}) ---")
        num_p_day = self.params.get('num_periods_per_day',1)
        if not isinstance(num_p_day, int) or num_p_day <= 0: num_p_day = 1
        num_terms = self.params.get('num_terms',1)
        num_tracks = self.params.get('num_concurrent_tracks_per_period', 1)
        current_schedule = {t: {d: [[None]*num_tracks for _ in range(num_p_day)] for d in DAYS_OF_WEEK} for t in range(1, num_terms + 1)}
        
        items_by_term = defaultdict(list) # This will store the full detail of courses for each term
        source_data = self.subjects_data if self.params.get('school_type') == 'Elementary' else self.courses_data
        
        # --- Critical input checks (early exit if fundamental data is missing/invalid) ---
        if not source_data: 
            self._log_message("No subjects/courses defined. Cannot generate schedule.", "ERROR")
            return None, self.current_run_log, False, {'overall_completion_rate': 0, 'unmet_grade_slots_count': float('inf'), 'unmet_prep_teachers_count': float('inf'), 'log_summary': ["No subjects/courses defined."]}
        if not self.teachers_data: 
            self._log_message("No teachers defined. Cannot generate schedule.", "ERROR")
            return None, self.current_run_log, False, {'overall_completion_rate': 0, 'unmet_grade_slots_count': float('inf'), 'unmet_prep_teachers_count': float('inf'), 'log_summary': ["No teachers defined."]}

        # Populate items_by_term with deep copies to allow modification during scheduling
        for item_data_orig in source_data:
            item_data = copy.deepcopy(item_data_orig)
            if item_data is None : continue
            term_num_item = item_data.get('term_assignment', 1)
            is_elem = self.params.get('school_type') == 'Elementary'
            terms_to_sched_in = list(range(1, num_terms + 1)) if is_elem and num_terms > 1 else [term_num_item]
            for term_actual in terms_to_sched_in:
                if term_actual > num_terms: continue
                items_by_term[term_actual].append({
                    **item_data, # Spread all original course data
                    'teacher': None, # Will be assigned by scheduler
                    'periods_to_schedule_this_week': item_data.get('periods_per_week', item_data.get('periods_per_week_in_active_term', 0)),
                    'constraints': item_data.get('parsed_constraints', []), # Ensure this is present
                    'type': 'subject' if is_elem else 'course',
                    'placed_this_term_count': 0, # Tracks how many instances are placed
                    'preferred_period_this_term': None, # Tracks if a consistent period is found
                    'is_cts_course': "cts" in item_data.get('name','').lower() if not is_elem else False,
                })

        teacher_max_teaching_this_week = {}
        for teacher in self.teachers_data:
            teacher_name = teacher['name']; total_avail_slots = 0
            for day_k in DAYS_OF_WEEK:
                for period_k in range(num_p_day):
                    if teacher.get('availability', {}).get(day_k, {}).get(period_k, False): total_avail_slots += 1
            max_t = total_avail_slots - MIN_PREP_BLOCKS_PER_WEEK
            teacher_max_teaching_this_week[teacher_name] = max_t
            if max_t < 0: self._log_message(f"WARN Teacher {teacher_name}: {total_avail_slots} avail, < {MIN_PREP_BLOCKS_PER_WEEK} prep. Max teach {max_t}. Cannot teach.", "WARN")
        
        # Initialize success status and metrics for this attempt
        is_successful_attempt = True
        attempt_metrics = {
            'overall_completion_rate': 0.0,
            'unmet_grade_slots_count': 0,
            'unmet_prep_teachers_count': 0,
            'log_summary': [] 
        }
        all_terms_overall_completion_rate = []

        # --- Main Scheduling Loop (Term by Term) ---
        for term_idx in range(1, num_terms + 1):
            term_log_messages = [] # Collect log messages for this term
            current_term_course_list_for_scheduling = items_by_term[term_idx]

            teacher_busy_this_term, item_scheduled_on_day_this_term = defaultdict(set), defaultdict(set)
            teacher_teaching_periods_this_week_for_term = defaultdict(int)
            must_assign_items, flexible_items_all = [], []
            
            for item_sort in current_term_course_list_for_scheduling: 
                (must_assign_items if any(c.get('type') == 'ASSIGN' for c in item_sort.get('constraints',[])) else flexible_items_all).append(item_sort)
            
            # 1. Schedule "ASSIGN" items first (critical, so failures here are likely showstoppers)
            for item in must_assign_items:
                item_name, item_subj_area = item['name'], item.get('subject_area')
                assign_constr = [c for c in item.get('constraints',[]) if c.get('type') == 'ASSIGN']
                num_assign_slots = len(assign_constr)
                
                if not item_subj_area: 
                    term_log_messages.append(f"[ERROR] CRIT: ASSIGN item '{item_name}' missing subject. Cannot schedule term.")
                    # Return immediately as this is a hard, unrecoverable failure for the current term
                    return current_schedule, self.current_run_log + term_log_messages, False, {'overall_completion_rate': 0, 'unmet_grade_slots_count': float('inf'), 'unmet_prep_teachers_count': float('inf'), 'log_summary': [f"ASSIGN item '{item_name}' missing subject."]}
                
                teacher_for_all = None
                potential_teachers_for_assign = [t for t in self.teachers_data if self._is_teacher_qualified(t, item_subj_area)]
                random.shuffle(potential_teachers_for_assign) # Randomize teacher selection for fairness
                for t_obj_cand in potential_teachers_for_assign:
                    cand_name = t_obj_cand['name']
                    if teacher_teaching_periods_this_week_for_term.get(cand_name,0) + num_assign_slots > teacher_max_teaching_this_week.get(cand_name, -1): continue
                    all_specific_slots_available = True
                    for slot_c in assign_constr:
                        day_c, period_c = slot_c['day'], slot_c['period']
                        if not t_obj_cand.get('availability',{}).get(day_c,{}).get(period_c,False) or (day_c,period_c) in teacher_busy_this_term.get(cand_name,set()): all_specific_slots_available = False; break
                    if all_specific_slots_available: teacher_for_all = cand_name; break
                
                if not teacher_for_all: 
                    term_log_messages.append(f"[ERROR] CRIT: No teacher for ASSIGN slots of '{item_name}'. Cannot schedule term.")
                    return current_schedule, self.current_run_log + term_log_messages, False, {'overall_completion_rate': 0, 'unmet_grade_slots_count': float('inf'), 'unmet_prep_teachers_count': float('inf'), 'log_summary': [f"No teacher for ASSIGN slots of '{item_name}'."]}
                
                item['teacher'] = teacher_for_all; slots_placed_ok_count = 0
                for slot_c in assign_constr:
                    day_c, period_c = slot_c['day'], slot_c['period']
                    if any((nc.get('day')==day_c or nc.get('day') is None) and nc.get('period')==period_c for nc in item.get('constraints',[]) if nc.get('type')=='NOT'): 
                        term_log_messages.append(f"[ERROR] CRIT: ASSIGN slot {day_c}-P{period_c+1} for '{item_name}' conflicts NOT constraint. Cannot schedule term.")
                        return current_schedule, self.current_run_log + term_log_messages, False, {'overall_completion_rate': 0, 'unmet_grade_slots_count': float('inf'), 'unmet_prep_teachers_count': float('inf'), 'log_summary': [f"ASSIGN conflicts NOT for '{item_name}'."]}
                    
                    track_found_assign = False
                    for track_idx_assign in range(num_tracks):
                        if current_schedule[term_idx][day_c][period_c][track_idx_assign] is None:
                            if self._check_cohort_clash_in_slot(item_name, term_idx, day_c, period_c, current_schedule): continue
                            current_schedule[term_idx][day_c][period_c][track_idx_assign] = (item_name, teacher_for_all); track_found_assign = True; slots_placed_ok_count +=1; break
                    
                    if not track_found_assign: 
                        term_log_messages.append(f"[ERROR] CRIT: No track in ASSIGN slot {day_c}-P{period_c+1} for '{item_name}'. Cannot schedule term.")
                        return current_schedule, self.current_run_log + term_log_messages, False, {'overall_completion_rate': 0, 'unmet_grade_slots_count': float('inf'), 'unmet_prep_teachers_count': float('inf'), 'log_summary': [f"No track for ASSIGN '{item_name}'."]}
                
                item['placed_this_term_count'] = slots_placed_ok_count
                for slot_c in assign_constr: teacher_busy_this_term[teacher_for_all].add((slot_c['day'], slot_c['period'])); item_scheduled_on_day_this_term[item_name].add(slot_c['day'])
                teacher_teaching_periods_this_week_for_term[teacher_for_all] += num_assign_slots
                term_log_messages.append(f"[DEBUG] ASSIGNED: '{item_name}' (T:{teacher_for_all}) to {num_assign_slots} slots. Load: {teacher_teaching_periods_this_week_for_term[teacher_for_all]}/{teacher_max_teaching_this_week.get(teacher_for_all, 'N/A')}")
            
            # 2. Schedule "Flexible" items
            flexible_items_processed = sorted(flexible_items_all, key=lambda x: (x.get('periods_to_schedule_this_week',0), len(x.get('constraints',[]))), reverse=True)
            if attempt_seed_modifier > 0 : random.seed(datetime.datetime.now().microsecond + attempt_seed_modifier + term_idx); random.shuffle(flexible_items_processed)
            
            period_indices_base = list(range(num_p_day))
            for item in flexible_items_processed:
                item_name, item_subj_area = item['name'], item.get('subject_area')
                not_constr = [c for c in item.get('constraints',[]) if c.get('type')=='NOT']
                periods_to_place = item.get('periods_to_schedule_this_week',0); item_teacher = item.get('teacher'); item['preferred_period_this_term'] = item.get('preferred_period_this_term', None)
                
                if not item_subj_area: 
                    term_log_messages.append(f"[WARN] Flex item '{item_name}' missing subject. Skipping.")
                    continue
                if periods_to_place == 0: item['placed_this_term_count'] = 0; continue
                
                num_already_placed = item.get('placed_this_term_count', 0)
                num_remaining_to_place = periods_to_place - num_already_placed
                if num_remaining_to_place <= 0: continue
                
                item_specific_days_order = DAYS_OF_WEEK[:] # Create a mutable copy
                is_3_credit_mwf = item.get('credits') == 3 and item.get('type') == 'course'
                is_cts_tth = item.get('is_cts_course', False)
                
                # Apply scheduling preferences (MWF for 3-credit, T/Th for CTS)
                preferred_days, other_days = [], []
                if is_3_credit_mwf and is_cts_tth: preferred_days = ["Monday", "Wednesday", "Friday"]; term_log_messages.append(f"[TRACE] Course '{item_name}' (3cr & CTS), prefer MWF.")
                elif is_3_credit_mwf: preferred_days = ["Monday", "Wednesday", "Friday"]; term_log_messages.append(f"[TRACE] Course '{item_name}' (3cr), prefer MWF.")
                elif is_cts_tth: preferred_days = ["Tuesday", "Thursday"]; term_log_messages.append(f"[TRACE] Course '{item_name}' (CTS), prefer T/Th.")
                
                if preferred_days: 
                    other_days = [d for d in DAYS_OF_WEEK if d not in preferred_days]
                    random.shuffle(preferred_days)
                    random.shuffle(other_days)
                    item_specific_days_order = preferred_days + other_days
                else: 
                    random.shuffle(period_indices_base) # Shuffle periods if no specific preference
                    item_specific_days_order = random.sample(DAYS_OF_WEEK, len(DAYS_OF_WEEK)) # Shuffle days

                for i_instance in range(num_remaining_to_place):
                    slot_found_this_instance = False
                    # IMPORTANT: Use the potentially re-shuffled period_indices_base for each instance
                    period_search_order = period_indices_base[:] 
                    if item['preferred_period_this_term'] is not None: 
                        # If a preferred period from a previous placement, try it first
                        period_search_order = [item['preferred_period_this_term']] + [p for p in period_indices_base if p != item['preferred_period_this_term']]
                    
                    for day_name_flex in item_specific_days_order:
                        if slot_found_this_instance: break
                        if not self.params.get('multiple_times_same_day',True) and day_name_flex in item_scheduled_on_day_this_term.get(item_name,set()): continue
                        
                        for period_idx_flex in period_search_order:
                            if slot_found_this_instance: break
                            if any((nc.get('day')==day_name_flex or nc.get('day') is None) and nc.get('period')==period_idx_flex for nc in not_constr): continue
                            if self._check_cohort_clash_in_slot(item_name, term_idx, day_name_flex, period_idx_flex, current_schedule): continue
                            
                            for track_idx_flex in range(num_tracks):
                                if current_schedule[term_idx][day_name_flex][period_idx_flex][track_idx_flex] is None:
                                    teacher_for_slot = self._find_qualified_teacher(item_subj_area, day_name_flex, period_idx_flex, teacher_busy_this_term, teacher_teaching_periods_this_week_for_term, teacher_max_teaching_this_week, item_teacher)
                                    if teacher_for_slot:
                                        if not item_teacher: item_teacher = teacher_for_slot; item['teacher'] = item_teacher # Assign teacher if not already assigned
                                        if item_teacher == teacher_for_slot: # Ensure same teacher for multi-period courses
                                            current_schedule[term_idx][day_name_flex][period_idx_flex][track_idx_flex] = (item_name, item_teacher)
                                            teacher_busy_this_term[item_teacher].add((day_name_flex, period_idx_flex))
                                            item_scheduled_on_day_this_term[item_name].add(day_name_flex)
                                            teacher_teaching_periods_this_week_for_term[item_teacher] += 1
                                            item['placed_this_term_count'] += 1
                                            slot_found_this_instance = True
                                            if item['preferred_period_this_term'] is None: item['preferred_period_this_term'] = period_idx_flex # Set preferred period after first placement
                                            break # Found a track for this instance
                            if slot_found_this_instance: break # Found a slot for this instance
                        if slot_found_this_instance: break # Found a day for this instance
                    
                    if not slot_found_this_instance: 
                        term_log_messages.append(f"[WARN] ALERT: No slot for instance #{num_already_placed + i_instance + 1} of '{item_name}'. Placed {item.get('placed_this_term_count',0)}/{periods_to_place}.")
                        break # Cannot place this instance, stop trying for this item

                final_placed_count = item.get('placed_this_term_count', 0)
                if final_placed_count == periods_to_place: term_log_messages.append(f"[DEBUG] SCHED: Flex item '{item_name}' (T:{item_teacher or 'Unassign!'}) all {final_placed_count} pds.")
                elif final_placed_count > 0 : term_log_messages.append(f"[WARN] PARTIAL: '{item_name}' (T:{item_teacher or 'Unassign!'}) {final_placed_count}/{periods_to_place}.")
            
            # --- Post-Scheduling Validation & Metric Collection for the current term ---
            total_periods_needed_term = sum(it.get('periods_to_schedule_this_week',0) for it in current_term_course_list_for_scheduling); 
            total_periods_placed_term = sum(it.get('placed_this_term_count',0) for it in current_term_course_list_for_scheduling)
            
            term_completion_rate = 0.0
            if total_periods_needed_term > 0:
                term_completion_rate = total_periods_placed_term / total_periods_needed_term
                term_log_messages.append(f"[INFO] Term {term_idx} Completion: {total_periods_placed_term}/{total_periods_needed_term} ({term_completion_rate*100:.2f}%).")
                if term_completion_rate < MIN_ACCEPTABLE_SCHEDULE_COMPLETION_RATE:
                    term_log_messages.append(f"[ERROR] CRIT (Term {term_idx}): Completion ({term_completion_rate*100:.2f}%) < min. Invalid.")
                    is_successful_attempt = False 
            elif not current_term_course_list_for_scheduling: 
                term_log_messages.append(f"[INFO] Term {term_idx}: No items.")
            else: 
                term_log_messages.append(f"[INFO] Term {term_idx}: All items 0 pds.")
            
            all_terms_overall_completion_rate.append(term_completion_rate)

            # Verify Prep Blocks for this term
            term_log_messages.append(f"[DEBUG] --- Verifying Prep Term {term_idx} ---")
            for teacher_check in self.teachers_data:
                name_check = teacher_check['name']
                actual_teaching_this_term = teacher_teaching_periods_this_week_for_term.get(name_check, 0)
                total_personal_avail_this_config = 0
                for day_avail_check in DAYS_OF_WEEK:
                    for p_avail_check in range(num_p_day):
                        if teacher_check.get('availability',{}).get(day_avail_check,{}).get(p_avail_check, False): 
                            total_personal_avail_this_config +=1
                actual_prep = total_personal_avail_this_config - actual_teaching_this_term
                max_teach_allowed_for_teacher = teacher_max_teaching_this_week.get(name_check, -1)
                term_log_messages.append(f"[TRACE] T {name_check}: Teaches {actual_teaching_this_term}, AvailMap {total_personal_avail_this_config}, MaxTeach {max_teach_allowed_for_teacher}, Prep {actual_prep} (Min: {MIN_PREP_BLOCKS_PER_WEEK})")
                
                if max_teach_allowed_for_teacher < 0 and actual_teaching_this_term > 0 : 
                    term_log_messages.append(f"[ERROR] CRIT (Term {term_idx}): Unscheduleable T {name_check} taught. Invalid.")
                    is_successful_attempt = False
                    attempt_metrics['unmet_prep_teachers_count'] += 1 # Accumulate across terms
                elif actual_prep < MIN_PREP_BLOCKS_PER_WEEK: 
                    term_log_messages.append(f"[ERROR] CRIT (Term {term_idx}): T {name_check} has {actual_prep} prep, < {MIN_PREP_BLOCKS_PER_WEEK}. Invalid.")
                    is_successful_attempt = False
                    attempt_metrics['unmet_prep_teachers_count'] += 1 # Accumulate across terms
            term_log_messages.append(f"[DEBUG] Term {term_idx} prep blocks verified.")

            # Verify Full Block Grades for this term (High School only)
            if self.params.get('school_type') == 'High School':
                term_log_messages.append(f"[DEBUG] --- Verifying Full Block Grades {GRADES_REQUIRING_FULL_SCHEDULE} (Term {term_idx}) ---")
                for grade_to_check in GRADES_REQUIRING_FULL_SCHEDULE:
                    grade_schedule_filled = {day: [False]*num_p_day for day in DAYS_OF_WEEK}
                    for day_sch in DAYS_OF_WEEK:
                        for period_sch in range(num_p_day):
                            slot_has_course_for_grade = False
                            for track_sch in range(num_tracks):
                                scheduled_item_tuple = current_schedule[term_idx][day_sch][period_sch][track_sch]
                                if scheduled_item_tuple:
                                    full_item_details = None
                                    for item_in_term_list in current_term_course_list_for_scheduling: 
                                        if item_in_term_list['name'] == scheduled_item_tuple[0]:
                                            full_item_details = item_in_term_list
                                            break
                                    if full_item_details:
                                        item_grade_level = full_item_details.get('grade_level')
                                        if item_grade_level == grade_to_check or item_grade_level == "Mixed":
                                            grade_schedule_filled[day_sch][period_sch] = True
                                            slot_has_course_for_grade = True
                                            break 
                            if slot_has_course_for_grade: continue 
                    
                    unmet_slots_for_this_grade = 0
                    for day_check_fill in DAYS_OF_WEEK:
                        for period_check_fill in range(num_p_day):
                            if not grade_schedule_filled[day_check_fill][period_check_fill]:
                                term_log_messages.append(f"[ERROR] CRIT (Term {term_idx}): Grade {grade_to_check} no class {day_check_fill} P{period_check_fill+1}. Invalid.")
                                unmet_slots_for_this_grade += 1
                    if unmet_slots_for_this_grade > 0:
                        is_successful_attempt = False
                        attempt_metrics['unmet_grade_slots_count'] += unmet_slots_for_this_grade # Accumulate across terms and grades

                term_log_messages.append(f"[DEBUG] Term {term_idx}: Full block schedule verified for Grades {GRADES_REQUIRING_FULL_SCHEDULE}.")
            term_log_messages.append(f"[DEBUG] Term {term_idx} scheduling completed and verified.")
            
            attempt_metrics['log_summary'].extend(term_log_messages) # Add term-specific logs to overall summary
        
        # Calculate overall completion rate across all terms
        if all_terms_overall_completion_rate:
            attempt_metrics['overall_completion_rate'] = sum(all_terms_overall_completion_rate) / len(all_terms_overall_completion_rate)
        
        if is_successful_attempt:
            self._log_message("Full Schedule Generation Attempt Finished Successfully.", "INFO")
        else:
            self._log_message("Full Schedule Generation Attempt Failed Validation.", "INFO")

        # Return the schedule, its log, success status, and metrics
        return current_schedule, self.current_run_log + attempt_metrics['log_summary'], is_successful_attempt, attempt_metrics

    def _calculate_period_times_for_display(self):
        num_p, p_dur, b_dur = self.params.get('num_periods_per_day',0), self.params.get('period_duration_minutes',0), self.params.get('break_between_classes_minutes',0)
        s_start_t, l_start_t, l_end_t = self.params.get('school_start_time'), self.params.get('lunch_start_time'), self.params.get('lunch_end_time')
        if not all([isinstance(num_p, int) and num_p > 0, isinstance(p_dur, int) and p_dur > 0, s_start_t, l_start_t, l_end_t]): return [f"P{i+1}" for i in range(num_p if isinstance(num_p, int) and num_p > 0 else 1)]
        s_start_m, l_start_m, l_end_m = time_to_minutes(s_start_t), time_to_minutes(l_start_t), time_to_minutes(l_end_t)
        times, current_m = [], s_start_m
        for i in range(num_p):
            if l_start_m <= current_m < l_end_m: current_m = l_end_m
            period_start_candidate, period_end_candidate = current_m, current_m + p_dur
            if period_start_candidate < l_start_m and period_end_candidate > l_start_m: current_m = l_end_m; period_start_candidate, period_end_candidate = current_m, current_m + p_dur
            if l_start_m <= period_start_candidate < l_end_m: period_start_candidate, period_end_candidate = l_end_m, l_end_m + p_dur
            times.append(f"{format_time_from_minutes(period_start_candidate)}-{format_time_from_minutes(period_end_candidate)}")
            current_m = period_end_candidate
            if i < num_p -1 : current_m += b_dur
        return times

    def display_schedules_console(self):
        if not self.generated_schedules_details: print("No schedules generated to display."); return
        period_times = self._calculate_period_times_for_display(); num_p = self.params.get('num_periods_per_day',0); num_tracks = self.params.get('num_concurrent_tracks_per_period', 1)
        if not isinstance(num_p, int) or num_p <= 0: num_p = 1
        for sched_detail in self.generated_schedules_details:
            s_id, schedule, log = sched_detail['id'], sched_detail['schedule'], sched_detail['log']
            print(f"\n\n--- TIMETABLE - SCHEDULE ID: {s_id} ---")
            
            # Display metrics for best failed attempt
            if s_id == "Best_Failed_Attempt" and 'metrics' in sched_detail:
                metrics = sched_detail['metrics']
                print(f"  (Failed Attempt Metrics: Overall Course Periods Placed: {metrics['overall_completion_rate']*100:.2f}%, Unmet Grade Slots: {metrics['unmet_grade_slots_count']}, Teachers with Insufficient Prep: {metrics['unmet_prep_teachers_count']})")

            log_key = f'view_log_sched_{s_id}_{random.randint(1000,9999)}'
            if self.get_input_with_default(log_key, f"View log for Sched {s_id}?", str, lambda x:x.lower() in ['yes','no'], choices=['yes','no']).lower()=='yes': print(f"\n--- Log for Sched ID: {s_id} ---"); [print(entry) for entry in log]; print("--- End Log ---")
            
            for term_idx, term_data in schedule.items():
                print(f"\n--- Term {term_idx} (Sched ID: {s_id}) ---"); header = ["Period/Time"] + DAYS_OF_WEEK; table_data = [header]
                for p_idx in range(num_p):
                    p_label = f"P{p_idx+1}";
                    if p_idx < len(period_times) and not period_times[p_idx].startswith("P"): p_label += f"\n{period_times[p_idx]}"
                    row_content = [p_label]
                    for day_name in DAYS_OF_WEEK:
                        cell_entries = []
                        for track_idx in range(num_tracks):
                            entry = term_data[day_name][p_idx][track_idx]; trk_lab = f"[Trk{track_idx+1}] " if num_tracks > 1 else ""
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
        num_s = len(self.generated_schedules_details); base_fn = f"{safe_name}_Schedules_{today}"; final_fn = f"{base_fn}.pdf" if num_s == 1 else f"{base_fn}_(1_to_{num_s}).pdf"
        print(f"\n--- Exporting {num_s} Schedule(s) to PDF: {final_fn} ---")
        try:
            doc = SimpleDocTemplate(final_fn, pagesize=landscape(letter)); styles = getSampleStyleSheet(); story = []
            period_times_pdf = self._calculate_period_times_for_display(); num_p = self.params.get('num_periods_per_day',0); num_tracks = self.params.get('num_concurrent_tracks_per_period', 1)
            if not isinstance(num_p, int) or num_p <= 0: num_p = 1
            for i, sched_detail in enumerate(self.generated_schedules_details):
                s_id, schedule = sched_detail['id'], sched_detail['schedule']
                
                story.append(Paragraph(f"Master Schedule - {self.params.get('school_name', 'N/A')} (ID: {s_id})", styles['h1']))
                if s_id == "Best_Failed_Attempt" and 'metrics' in sched_detail:
                    metrics = sched_detail['metrics']
                    story.append(Paragraph(f"<i>(Best Failed Attempt: Overall Course Periods Placed: {metrics['overall_completion_rate']*100:.2f}%, Unmet Grade Slots: {metrics['unmet_grade_slots_count']}, Teachers with Insufficient Prep: {metrics['unmet_prep_teachers_count']})</i>", styles['Normal']))
                story.append(Paragraph(f"Generated: {today}", styles['Normal'])); story.append(Spacer(1, 0.2*72))
                
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
                                entry = term_data[day_name][p_idx][track_idx]; trk_lab_pdf = f"<i>Trk{track_idx+1}:</i> " if num_tracks > 1 else ""
                                if entry and entry[0]: cell_paras.append(Paragraph(f"{trk_lab_pdf}{entry[0]}<br/>({entry[1] if entry[1] else 'No T.'})", styles['Normal']))
                                else: cell_paras.append(Paragraph(f"{trk_lab_pdf}---", styles['Normal']))
                            row_pdf.append(cell_paras)
                        pdf_data.append(row_pdf)
                    pw, _ = landscape(letter); aw = pw - 1.5*72; col_w = [aw*0.15] + [(aw*0.85)/len(DAYS_OF_WEEK)]*len(DAYS_OF_WEEK)
                    table = Table(pdf_data, colWidths=col_w, repeatRows=1)
                    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor("#CCCCCC")),('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('FONTNAME',(0,0),(-1,-1),'Helvetica'),('FONTSIZE',(0,0),(-1,-1),7),('GRID',(0,0),(-1,-1),0.5,colors.black),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
                    story.append(table); story.append(Spacer(1, 0.2*72))
                if i < num_s - 1: story.append(PageBreak()) # Add page break only between schedules
            doc.build(story); print(f"Schedule(s) exported to {final_fn}")
        except ImportError: print("`reportlab` not found. PDF export failed.")
        except Exception as e: print(f"PDF export error: {e}"); traceback.print_exc()

    def run_once(self):
        print("\n--- Starting New Schedule Generation Run ---"); self.current_run_log = []
        self.display_info_needed(); self.get_school_type(); self.get_operational_parameters(); self.get_course_structure_model(); self.get_period_structure_details()
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

        if self.params.get('school_type') == 'Elementary': self.get_elementary_subjects()
        elif self.params.get('school_type') == 'High School': self.get_high_school_courses(); self.get_general_constraints()
        else: 
            print("School type not set. Cannot proceed."); 
            self._log_message("CRITICAL: School type not set. Exiting.", "ERROR")
            return
        
        if (self.params.get('school_type') == 'Elementary' and not self.subjects_data) or (self.params.get('school_type') == 'High School' and not self.courses_data): 
            print("No subjects/courses defined. Cannot generate a schedule."); 
            self._log_message("CRITICAL: No subjects/courses defined. Exiting.", "ERROR")
            return
        
        num_schedules_key = f"num_schedules_to_generate_{random.randint(1000,9999)}"
        num_schedules_to_generate = self.get_input_with_default(num_schedules_key, f"How many distinct valid schedules to attempt (1-{MAX_DISTINCT_SCHEDULES_TO_GENERATE})?", int, lambda x: 1 <= x <= MAX_DISTINCT_SCHEDULES_TO_GENERATE, default_value_override=1)
        
        self.generated_schedules_details = [] # This will store successful schedules OR the best failed one at the end
        generated_schedule_hashes = set()

        best_failed_schedule_data = {
            'schedule': None,
            'log': [],
            # Initialize metrics with worst possible values
            'metrics': {'overall_completion_rate': 0.0, 'unmet_grade_slots_count': float('inf'), 'unmet_prep_teachers_count': float('inf')}
        }

        total_attempts_for_all = MAX_SCHEDULE_GENERATION_ATTEMPTS * num_schedules_to_generate
        for attempt_num in range(total_attempts_for_all):
            if len(self.generated_schedules_details) >= num_schedules_to_generate: 
                self._log_message(f"Generated requested {num_schedules_to_generate} distinct schedules.", "INFO")
                break # Exit if enough successful schedules are found
            
            print(f"\n--- Overall Schedule Gen Attempt {attempt_num + 1}/{total_attempts_for_all} (aiming for {num_schedules_to_generate}, found {len(self.generated_schedules_details)}) ---")
            
            # Call the modified generate_single_schedule_attempt
            attempt_schedule, attempt_log, is_attempt_successful, attempt_metrics = \
                self.generate_single_schedule_attempt(attempt_seed_modifier=attempt_num)
            
            # Check for fundamental input errors (where generate_single_schedule_attempt returns None directly)
            if attempt_schedule is None:
                print(f"CRITICAL ERROR: Fundamental input issues prevent scheduling. Check previous logs for details.")
                self.current_run_log.extend(["--- Log from fundamental error ---"] + attempt_log[-5:])
                return # Exit run_once immediately if fundamental error occurred

            if is_attempt_successful:
                try: 
                    schedule_hash = hash(json.dumps(attempt_schedule, sort_keys=True))
                except TypeError: 
                    # Fallback if schedule contains non-JSON serializable/hashable elements
                    schedule_hash = hash(str(attempt_schedule)) 
                
                if schedule_hash not in generated_schedule_hashes:
                    s_id = len(self.generated_schedules_details) + 1
                    self.generated_schedules_details.append({'id': s_id, 'schedule': attempt_schedule, 'log': attempt_log})
                    generated_schedule_hashes.add(schedule_hash)
                    print(f"SUCCESS: Found new distinct valid schedule (ID: {s_id}). Total distinct: {len(self.generated_schedules_details)}.")
                else: 
                    print(f"INFO: Generated a schedule identical to a previous one. Trying again.")
            else: # Attempt failed validation
                print(f"INFO: Attempt {attempt_num + 1} did not yield a valid schedule. "
                      f"(Completion: {attempt_metrics['overall_completion_rate']*100:.2f}%, "
                      f"Unmet Grades: {attempt_metrics['unmet_grade_slots_count']}, "
                      f"Unmet Prep: {attempt_metrics['unmet_prep_teachers_count']}).")
                
                # Logic to store the best failed attempt
                current_is_better = False
                # Primary sort: Fewer unmet grade slots are better
                if attempt_metrics['unmet_grade_slots_count'] < best_failed_schedule_data['metrics']['unmet_grade_slots_count']:
                    current_is_better = True
                # Secondary sort: If unmet grade slots are equal, fewer unmet prep teachers are better
                elif attempt_metrics['unmet_grade_slots_count'] == best_failed_schedule_data['metrics']['unmet_grade_slots_count']:
                    if attempt_metrics['unmet_prep_teachers_count'] < best_failed_schedule_data['metrics']['unmet_prep_teachers_count']:
                        current_is_better = True
                    # Tertiary sort: If both unmet counts are equal, higher completion rate is better
                    elif attempt_metrics['unmet_prep_teachers_count'] == best_failed_schedule_data['metrics']['unmet_prep_teachers_count']:
                        if attempt_metrics['overall_completion_rate'] > best_failed_schedule_data['metrics']['overall_completion_rate']:
                            current_is_better = True
                
                if current_is_better:
                    best_failed_schedule_data['schedule'] = attempt_schedule
                    best_failed_schedule_data['log'] = attempt_log
                    best_failed_schedule_data['metrics'] = attempt_metrics # Store full metrics
                    print("  This is the best failed attempt found so far.")

                if attempt_log: self.current_run_log.extend(["--- Log from failed attempt (summary) ---"] + attempt_log[-5:]) # Append last few lines from failed log

        # --- End of all attempts: Display results ---
        if not self.generated_schedules_details: 
            print(f"\nERROR: Could not generate any valid schedules after {total_attempts_for_all} attempts. Review inputs and logs for constraint violations.")
            if best_failed_schedule_data['schedule']:
                print("\n--- Displaying Best Failed Schedule Attempt ---")
                best_failed_schedule_data['id'] = "Best_Failed_Attempt" # Assign a pseudo-ID for display
                self.generated_schedules_details.append(best_failed_schedule_data) # Add to list for display functions
            else:
                print("No schedule could even be partially generated due to fundamental input issues or extreme constraints.")
        else: 
            print(f"\nSUCCESS: Generated {len(self.generated_schedules_details)} distinct valid schedule(s).")
        
        # Display schedules in console and offer PDF export
        if self.generated_schedules_details: 
            self.display_schedules_console()
            export_key = f'export_pdf_choice_{random.randint(1000,9999)}'
            if self.get_input_with_default(export_key, "\nExport generated schedule(s) to PDF?", str, lambda x: x.lower() in ['yes','no'], choices=['yes','no']).lower() == 'yes': 
                self.export_schedules_pdf()
        
        # Offer to view the main run log
        log_main_key = f'view_main_run_log_{random.randint(1000,9999)}'
        if self.get_input_with_default(log_main_key, "View main operational log for this run?", str, lambda x:x.lower() in ['yes','no'], choices=['yes','no']).lower()=='yes': 
            print("\n--- Main Operational Log ---"); 
            [print(msg) for msg in self.current_run_log]; 
            print("--- End Main Log ---")

    def run(self):
        print("Welcome to the School Scheduler!")
        try:
            # Attempt to load previous session cache
            if os.path.exists("scheduler_session_cache.tmp"):
                with open("scheduler_session_cache.tmp", "r") as f: loaded_cache_raw = json.load(f)
                self.session_cache = loaded_cache_raw
                # Attempt to parse specific parameters from cached strings to correct types
                param_keys_from_cache = {
                    'num_periods_per_day': int, 'min_instructional_hours': int, 'num_terms': int, 
                    'weeks_per_term': int, 'instructional_days': int, 'num_instructional_weeks': int, 
                    'break_between_classes_minutes': int, 'num_concurrent_tracks_per_period': int,
                    'total_annual_instructional_hours': float, 'school_type': str, 'scheduling_model': str,
                    'school_name': str, 'start_date_str': str, 'end_date_str': str, 'non_instructional_days_str': str, 
                    'start_time_str': str, 'end_time_str': str, 'lunch_start_time_str': str, 'lunch_end_time_str': str,
                    'multiple_times_same_day_choice': str}
                for p_key, expected_type in param_keys_from_cache.items():
                    if p_key in self.session_cache:
                        try:
                            if p_key == 'multiple_times_same_day_choice': self.params['multiple_times_same_day'] = (self.session_cache[p_key].lower() == 'yes')
                            elif self.session_cache[p_key] is not None: self.params[p_key] = expected_type(self.session_cache[p_key])
                        except (ValueError, TypeError) as e:
                            self._log_message(f"Cache Load Error: param '{p_key}' val '{self.session_cache.get(p_key)}' to {expected_type.__name__}: {e}. Using default.", "WARN")
                            if p_key == 'num_periods_per_day': self.params[p_key] = 1 
                            elif p_key == 'num_terms': self.params[p_key] = 1 
                # Load high school credits database
                if 'high_school_credits_db' in self.session_cache: self.high_school_credits_db = copy.deepcopy(self.session_cache['high_school_credits_db'])
                else: self.high_school_credits_db = copy.deepcopy(HIGH_SCHOOL_COURSE_CREDITS_TEMPLATE)
                # Re-parse teacher availability based on loaded num_periods_per_day
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
                self._log_message(f"Loaded previous session. num_periods={self.params.get('num_periods_per_day', 'N/A')}.", "INFO")
                print("INFO: Loaded previous session data.")
            else: self.session_cache = {}; self.high_school_credits_db = copy.deepcopy(HIGH_SCHOOL_COURSE_CREDITS_TEMPLATE); print("INFO: No previous session cache file found. Starting fresh.")
        except json.JSONDecodeError as e: self.session_cache = {}; self.high_school_credits_db = copy.deepcopy(HIGH_SCHOOL_COURSE_CREDITS_TEMPLATE); print(f"WARN: Could not decode session cache ({e}). Starting fresh.")
        except Exception as e_load: self.session_cache = {}; self.high_school_credits_db = copy.deepcopy(HIGH_SCHOOL_COURSE_CREDITS_TEMPLATE); print(f"WARN: Error loading session cache ({type(e_load).__name__}: {e_load}). Starting fresh."); traceback.print_exc()

        while True:
            current_run_cache_backup = copy.deepcopy(self.session_cache) 
            try:
                self.run_once()
                try:
                    self.session_cache['high_school_credits_db'] = copy.deepcopy(self.high_school_credits_db) 
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
            print("\n" + "="*25 + " RESTARTING WITH MODIFICATIONS " + "="*25 + "\n")
        print("\n--- Script Finished ---")

if __name__ == "__main__":
    scheduler_app = SchoolScheduler()
    scheduler_app.run()
