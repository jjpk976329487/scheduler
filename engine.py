import datetime
import math
import random
import copy
import json
import calendar
from collections import defaultdict

# --- Constants ---
ELEMENTARY_MIN_HOURS = 950
HIGH_SCHOOL_MIN_HOURS = 1000
DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
CREDITS_TO_HOURS_PER_CREDIT = 25
TYPICAL_COURSE_CREDITS_FOR_ESTIMATE = 5
MAX_SCHEDULE_GENERATION_ATTEMPTS = 200 # As per original script, though not directly used by engine's generate_schedules single call
MAX_DISTINCT_SCHEDULES_TO_GENERATE = 10
MIN_PREP_BLOCKS_PER_WEEK = 2
MIN_ACCEPTABLE_SCHEDULE_COMPLETION_RATE = 0.75
GRADES_REQUIRING_FULL_SCHEDULE = [10, 11, 12]
PERIODS_PER_TYPICAL_OPTION_BLOCK = 5

QUALIFIABLE_SUBJECTS = [
    "Math", "Science", "Social Studies", "English", "French",
    "PE", "Cree", "CTS", "Other"
]

CORE_SUBJECTS_HS = ["English", "Math", "Science", "Social Studies"]

CTS_KEYWORDS = [
    "CTS", "Technology", "Computing", "Construction", "Design", "Fabrication",
    "Financial", "Foods", "Legal", "Mechanics", "Psychology",
    "Work Experience", "Special Projects", "Art", "Drama", "Music", "Outdoor Education"
]

COMBINABLE_PAIRS = [
    ("English 10-2", "English 10-4"), ("English 20-2", "English 20-4"),
    ("English 30-2", "English 30-4"), ("Social Studies 10-2", "Social Studies 10-4"),
    ("Social Studies 20-2", "Social Studies 20-4"), ("Math 10-3", "Math 10-4"),
    ("Math 20-3", "Math 20-4"), ("Math 30-3", "Math 30-4"),
    ("Science 14", "Science 10-4"), ("Science 24", "Science 20-4"),
]

HIGH_SCHOOL_COURSE_CREDITS_TEMPLATE = {
    # Grade 10
    "English 10-1": 5, "English 10-2": 5, "English 10-4": 5, "Social Studies 10-1": 5, "Social Studies 10-2": 5, "Social Studies 10-4": 5, "Math 10C": 5, "Math 10-3": 5, "Math 10-4": 5, "Science 10": 5, "Science 14": 5, "Science 10-4": 5, "Physical Education 10": 5, "CALM 20": 3, "Art 10": 3, "Drama 10": 3, "Music 10": 3, "French 10": 5, "Outdoor Education 10": 3, "Information Processing 10": 1, "Communication Technology 10": 5, "Computing Science 10": 5, "Construction Technologies 10": 5, "Design Studies 10": 5, "Fabrication Studies 10": 5, "Financial Management 10": 5, "Foods 10": 5, "Legal Studies 10": 5, "Mechanics 10": 5,
    # Grade 11
    "English 20-1": 5, "English 20-2": 5, "English 20-4": 5, "Social Studies 20-1": 5, "Social Studies 20-2": 5, "Social Studies 20-4": 5, "Math 20-1": 5, "Math 20-2": 5, "Math 20-3": 5, "Math 20-4": 5, "Biology 20": 5, "Chemistry 20": 5, "Physics 20": 5, "Science 20": 5, "Science 24": 5, "Science 20-4": 5, "Art 20": 3, "Drama 20": 3, "Music 20": 3, "French 20": 5, "Outdoor Education 20": 3, "Information Processing 20": 1, "Communication Technology 20": 5, "Computing Science 20": 5, "Construction Technologies 20": 5, "Design Studies 20": 5, "Fabrication Studies 20": 5, "Financial Management 20": 5, "Foods 20": 5, "Legal Studies 20": 5, "Mechanics 20": 5, "Personal Psychology 20": 3, "Work Experience 25": 3,
    # Grade 12
    "English 30-1": 5, "English 30-2": 5, "English 30-4": 5, "Social Studies 30-1": 5, "Social Studies 30-2": 5, "Math 30-1": 5, "Math 30-2": 5, "Math 30-3": 5, "Math 30-4": 5, "Biology 30": 5, "Chemistry 30": 5, "Physics 30": 5, "Science 30": 5, "Art 30": 3, "Drama 30": 3, "Music 30": 3, "French 30": 5, "Outdoor Education 30": 3, "Information Processing 30": 1, "Communication Technology 30": 5, "Computing Science 30": 5, "Construction Technologies 30": 5, "Design Studies 30": 5, "Fabrication Studies 30": 5, "Financial Management 30": 5, "Foods 30": 5, "Legal Studies 30": 5, "Mechanics 30": 5, "General Psychology 30": 3, "Special Projects 30": 5, "Work Experience 35": 3,
}

CORE_COURSE_STREAMS = {
    "English": { 10: ["English 10-1", "English 10-2", "English 10-4"], 11: ["English 20-1", "English 20-2", "English 20-4"], 12: ["English 30-1", "English 30-2", "English 30-4"]},
    "Social Studies": { 10: ["Social Studies 10-1", "Social Studies 10-2", "Social Studies 10-4"], 11: ["Social Studies 20-1", "Social Studies 20-2", "Social Studies 20-4"], 12: ["Social Studies 30-1", "Social Studies 30-2"]},
    "Math": { 10: ["Math 10C", "Math 10-3", "Math 10-4"], 11: ["Math 20-1", "Math 20-2", "Math 20-3", "Math 20-4"], 12: ["Math 30-1", "Math 30-2", "Math 30-3", "Math 30-4"]},
    "Science": { 10: ["Science 10", "Science 14", "Science 10-4"], 11: ["Biology 20", "Chemistry 20", "Physics 20", "Science 20", "Science 24", "Science 20-4"], 12: ["Biology 30", "Chemistry 30", "Physics 30", "Science 30"]},
}

STAT_HOLIDAY_PATTERNS_FOR_DEFAULT = [
    {"month": 1, "day": 1, "name": "New Year's Day"}, {"month": 9, "nth_weekday": 1, "weekday": 0, "name": "Labour Day"},
    {"month": 10, "nth_weekday": 2, "weekday": 0, "name": "Thanksgiving Day (CA)"}, {"month": 11, "day": 11, "name": "Remembrance Day"},
    {"month": 12, "day": 25, "name": "Christmas Day"}, {"month": 12, "day": 26, "name": "Boxing Day"},
    {"month": 2, "nth_weekday": 3, "weekday": 0, "name": "Family Day (AB)"}, # Example
]

def _get_date_for_nth_weekday_of_month(year, month, nth_weekday_val, weekday_target):
    if not (1 <= month <= 12 and 1 <= nth_weekday_val <= 5 and 0 <= weekday_target <= 6): return None
    first_day_weekday, days_in_month = calendar.monthrange(year, month)
    day_offset = (weekday_target - first_day_weekday + 7) % 7
    nth_occurrence_day = 1 + day_offset + (nth_weekday_val - 1) * 7
    return datetime.date(year, month, nth_occurrence_day) if nth_occurrence_day <= days_in_month else None

def parse_time(time_str):
    for fmt in ("%I:%M %p", "%H:%M"):
        try: return datetime.datetime.strptime(time_str, fmt).time()
        except (ValueError, TypeError): pass
    return None

def parse_date(date_str):
    try: return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError): return None

def time_to_minutes(time_obj): return time_obj.hour * 60 + time_obj.minute if time_obj else 0
def format_time_from_minutes(mins): return f"{int(mins // 60):02d}:{int(mins % 60):02d}" if mins is not None else ""

def calculate_instructional_days(start_date, end_date, non_instructional_days_str):
    non_instructional_dates = {parse_date(ds.strip()) for ds in non_instructional_days_str.split(',') if parse_date(ds.strip())}
    days = 0
    if start_date and end_date and start_date <= end_date:
        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() < 5 and current_date not in non_instructional_dates: days += 1
            current_date += datetime.timedelta(days=1)
    return days

def parse_teacher_availability(availability_str, num_periods):
    num_periods = num_periods if isinstance(num_periods, int) and num_periods > 0 else 1
    availability = {day: {p: True for p in range(num_periods)} for day in DAYS_OF_WEEK}
    if not availability_str or availability_str.lower() in ["always", "always available"]: return availability

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
            else: # Text-based availability
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
                    if not is_morn and not is_aft: # unavailable whole day
                         for p_idx in range(num_periods): availability[day_full][p_idx] = False
        except Exception: pass # Ignore malformed constraint parts
    return availability

def parse_scheduling_constraint(constraint_str, num_periods):
    parsed_constraints = []
    num_periods = num_periods if isinstance(num_periods, int) and num_periods > 0 else 1
    constraint_str_upper = constraint_str.upper().strip()
    type_val, content = None, ""

    if constraint_str_upper.startswith("NOT "): type_val, content = "NOT", constraint_str[4:].strip()
    elif constraint_str_upper.startswith("ASSIGN "): type_val, content = "ASSIGN", constraint_str[7:].strip()
    else: return parsed_constraints

    if type_val == "ASSIGN":
        for slot_str in content.replace(',', ';').split(';'): # Allow both separators
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
                except ValueError: pass # Ignore if period is not a number
        return parsed_constraints

    target_day_not, parts_not = None, content.split()
    if parts_not:
        day_cand_upper = parts_not[0].upper()
        for day_name_iter in DAYS_OF_WEEK:
            if day_cand_upper == day_name_iter.upper() or day_cand_upper == day_name_iter[:3].upper():
                target_day_not = day_name_iter
                parts_not = parts_not[1:]
                break
    days_to_apply = [target_day_not] if target_day_not else DAYS_OF_WEEK

    if not parts_not: # e.g., "NOT MONDAY" or "NOT" (implies all periods of specified day(s))
        for day_apply in days_to_apply:
            for p_idx in range(num_periods):
                parsed_constraints.append({'type': 'NOT', 'day': day_apply, 'period': p_idx})
        return parsed_constraints

    spec_not = parts_not[0].upper()
    indices_to_constrain = []
    try:
        if spec_not.startswith("P"):
            period_part_not = spec_not[1:]
            if '-' in period_part_not:
                s_p_str, e_p_str = period_part_not.split('-')
                s_p, e_p = int(s_p_str)-1, int(e_p_str)-1
                indices_to_constrain.extend(range(s_p, e_p + 1))
            else: indices_to_constrain.append(int(period_part_not) - 1)
        elif spec_not == "AFTERNOON": indices_to_constrain.extend(range(num_periods // 2, num_periods))
        elif spec_not == "MORNING": indices_to_constrain.extend(range(0, num_periods // 2))
        elif spec_not == "LAST" and num_periods > 0: indices_to_constrain.append(num_periods - 1)
        elif spec_not == "FIRST" and num_periods > 0: indices_to_constrain.append(0)
    except ValueError: pass # Invalid period number/range

    for day_apply_final in days_to_apply:
        for p_idx_con in indices_to_constrain:
            if 0 <= p_idx_con < num_periods:
                parsed_constraints.append({'type': 'NOT', 'day': day_apply_final, 'period': p_idx_con})
    return parsed_constraints

class SchedulingEngine:
    def __init__(self):
        self.params = {}
        self.teachers_data = []
        self.courses_data = []
        self.subjects_data = []
        self.cohort_constraints = []
        self.high_school_credits_db = copy.deepcopy(HIGH_SCHOOL_COURSE_CREDITS_TEMPLATE)
        self.generated_schedules_details = []
        self.current_run_log = []

    def set_parameters(self, params_dict): self.params = copy.deepcopy(params_dict)
    def set_teachers(self, teachers_list): self.teachers_data = copy.deepcopy(teachers_list)
    def set_courses(self, courses_list): self.courses_data = copy.deepcopy(courses_list)
    def set_subjects(self, subjects_list): self.subjects_data = copy.deepcopy(subjects_list)
    def set_cohort_constraints(self, constraints_list): self.cohort_constraints = copy.deepcopy(constraints_list)
    def set_hs_credits_db(self, db_dict): self.high_school_credits_db = copy.deepcopy(db_dict)
    def get_parameters(self): return copy.deepcopy(self.params)
    def get_generated_schedules(self): return self.generated_schedules_details
    def get_run_log(self): return self.current_run_log

    def _log_message(self, message, level="INFO"):
        self.current_run_log.append(f"[{level}] {datetime.datetime.now().strftime('%H:%M:%S')} {message}")

    def suggest_non_instructional_days(self): # Renamed from _calculate_suggested_non_instructional_days
        start_date, end_date = self.params.get('start_date'), self.params.get('end_date')
        if not (start_date and end_date): self._log_message("Cannot suggest days: start/end date missing.", "DEBUG"); return ""
        
        non_instructional_dates = set()
        for year in range(start_date.year, end_date.year + 1):
            for pattern in STAT_HOLIDAY_PATTERNS_FOR_DEFAULT:
                holiday_date = None
                try:
                    if "day" in pattern: holiday_date = datetime.date(year, pattern["month"], pattern["day"])
                    elif "nth_weekday" in pattern: holiday_date = _get_date_for_nth_weekday_of_month(year, pattern["month"], pattern["nth_weekday"], pattern["weekday"])
                    if holiday_date and start_date <= holiday_date <= end_date: non_instructional_dates.add(holiday_date)
                except Exception as e: self._log_message(f"Could not calc holiday {pattern.get('name', 'Unknown')}: {e}", "WARN")
        try: # Christmas Break
            christmas_day = datetime.date(start_date.year, 12, 25)
            break_start = christmas_day - datetime.timedelta(days=christmas_day.weekday() + 7)
            for i in range(21): non_instructional_dates.add(break_start + datetime.timedelta(days=i))
        except Exception as e: self._log_message(f"Could not calc Christmas break: {e}", "WARN")
        try: # Spring Break
            spring_break_start = _get_date_for_nth_weekday_of_month(end_date.year, 3, 3, 0) # 3rd Mon of Mar
            if spring_break_start:
                for i in range(7): non_instructional_dates.add(spring_break_start + datetime.timedelta(days=i))
        except Exception as e: self._log_message(f"Could not calc Spring break: {e}", "WARN")
        
        # PD Days
        current_year, current_month, month_count = start_date.year, start_date.month, 0
        while datetime.date(current_year, current_month, 1) <= end_date:
            if month_count % 2 == 0: # Every other month
                pd_day = _get_date_for_nth_weekday_of_month(current_year, current_month, 1, 4) # 1st Friday
                if pd_day and start_date <= pd_day <= end_date and pd_day not in non_instructional_dates:
                    non_instructional_dates.add(pd_day)
            current_month += 1
            if current_month > 12: current_month, current_year = 1, current_year + 1
            month_count += 1
            
        return ", ".join([d.strftime("%Y-%m-%d") for d in sorted(list(non_instructional_dates)) if start_date <= d <= end_date])


    def suggest_core_courses(self): # Renamed from _get_suggested_core_courses
        self._log_message("Suggesting courses based on teacher and schedule capacity.", "INFO")
        suggested_courses_all_grades = []
        num_terms = self.params.get('num_terms', 1)
        num_p_day = self.params.get('num_periods_per_day', 1)

        if self.params.get('school_type') != 'High School' or num_terms == 0: return []
        if not self.teachers_data: self._log_message("Cannot suggest courses: No teachers defined.", "ERROR"); return []
            
        total_teacher_capacity_per_week = sum(max(0, sum(1 for day in DAYS_OF_WEEK for p_idx in range(num_p_day) if teacher.get('availability', {}).get(day, {}).get(p_idx, False)) - MIN_PREP_BLOCKS_PER_WEEK) for teacher in self.teachers_data)
        grid_capacity_per_week = self.params.get('num_concurrent_tracks_per_period', 1) * num_p_day * len(DAYS_OF_WEEK)
        effective_weekly_capacity_per_term = min(total_teacher_capacity_per_week, grid_capacity_per_week)
        
        self._log_message(f"Effective schedulable periods/wk per term: {effective_weekly_capacity_per_term}", "INFO")

        p_dur_min = self.params.get('period_duration_minutes', 1)
        weeks_per_term = self.params.get('weeks_per_term', 18)
        if self.params.get('scheduling_model') == "Full Year": weeks_per_term = self.params.get('num_instructional_weeks', 36)

        potential_courses = []
        for subject, grades in CORE_COURSE_STREAMS.items():
            for grade, courses in grades.items():
                for course_name in courses:
                    potential_courses.append({'name': course_name, 'subject': subject, 'grade': int(grade)}) # ensure grade is int

        potential_courses.append({'name': 'CALM 20', 'subject': 'Other', 'grade': 10, '_required': True})
        potential_courses.append({'name': 'Physical Education 10', 'subject': 'PE', 'grade': 10, '_required': True})

        potential_courses.sort(key=lambda c: (0 if c.get('_required') else (1 if (c['name'].endswith(("-1", "C")) or " 10" in c['name'] or " 20" in c['name'] or " 30" in c['name']) else (2 if (c['name'].endswith(("-2", " 14", " 24"))) else 3)), c['grade']))

        periods_used_by_term = defaultdict(int)
        
        def create_course_entry(course_name, subject_area, grade_level, term_num): # Local helper
            credits = self.high_school_credits_db.get(course_name)
            if credits is None: return None
            course_mins = credits * CREDITS_TO_HOURS_PER_CREDIT * 60
            periods_year = math.ceil(course_mins / p_dur_min) if p_dur_min > 0 else 0
            periods_week = math.ceil(periods_year / weeks_per_term) if weeks_per_term > 0 else 0
            return {'name': course_name, 'credits': credits, 'grade_level': grade_level,
                    'subject_area': subject_area, 'term_assignment': term_num,
                    'periods_per_week_in_active_term': max(1, periods_week), 'parsed_constraints':[],
                    'scheduling_constraints_raw': "", '_is_suggestion': True}

        cores_per_term = math.ceil(len(CORE_SUBJECTS_HS) / num_terms)
        assigned_core_subjects_by_grade_term = defaultdict(lambda: defaultdict(set))
        
        for course_info in potential_courses:
            term = 1 
            if num_terms > 1 and course_info['subject'] in ["Science", "Social Studies"]: term = 2
            
            entry = create_course_entry(course_info['name'], course_info['subject'], course_info['grade'], term)
            if not entry: continue

            if entry['subject_area'] in CORE_SUBJECTS_HS:
                current_assigned_term = entry['term_assignment']
                if len(assigned_core_subjects_by_grade_term[entry['grade_level']][current_assigned_term]) >= cores_per_term:
                    alt_term = next((t for t in range(1, num_terms + 1) if len(assigned_core_subjects_by_grade_term[entry['grade_level']][t]) < cores_per_term), None)
                    if alt_term: entry['term_assignment'] = alt_term
                    else: continue # Can't place this core course
                assigned_core_subjects_by_grade_term[entry['grade_level']][entry['term_assignment']].add(entry['subject_area'])

            periods_needed = entry['periods_per_week_in_active_term']
            target_term_for_placement = entry['term_assignment']
            if periods_used_by_term[target_term_for_placement] + periods_needed <= effective_weekly_capacity_per_term:
                if not any(c['name'] == entry['name'] for c in suggested_courses_all_grades):
                    suggested_courses_all_grades.append(entry)
                    periods_used_by_term[target_term_for_placement] += periods_needed
                    self._log_message(f"Suggested '{entry['name']}' ({periods_needed} p/wk in T{target_term_for_placement})", "DEBUG")

        all_cts_courses = [name for name in self.high_school_credits_db.keys() if any(kw.lower() in name.lower() for kw in CTS_KEYWORDS)]
        for term_fill in range(1, num_terms + 1):
            remaining_capacity = effective_weekly_capacity_per_term - periods_used_by_term[term_fill]
            suggested_names = {c['name'] for c in suggested_courses_all_grades}
            available_cts_for_term = [name for name in all_cts_courses if name not in suggested_names]
            random.shuffle(available_cts_for_term)

            while remaining_capacity >= 3 and available_cts_for_term: # Min 3 pds/wk for a course
                cts_name = available_cts_for_term.pop(0)
                entry = create_course_entry(cts_name, "CTS", "Mixed", term_fill)
                if not entry: continue
                periods_needed = entry['periods_per_week_in_active_term']
                if periods_needed > 0 and remaining_capacity >= periods_needed : # ensure periods_needed is positive
                    suggested_courses_all_grades.append(entry)
                    periods_used_by_term[term_fill] += periods_needed
                    remaining_capacity -= periods_needed
                    self._log_message(f"Filled capacity with CTS '{entry['name']}' ({periods_needed} p/wk in T{term_fill})", "DEBUG")
        
        return suggested_courses_all_grades

    def suggest_grouped_courses(self): # Renamed from _get_suggested_grouped_courses
        self._log_message("Suggesting GROUPED courses based on teacher and schedule capacity.", "INFO")
        suggested_grouped_courses = []
        num_terms = self.params.get('num_terms', 1)
        num_p_day = self.params.get('num_periods_per_day', 1)

        if self.params.get('school_type') != 'High School' or num_terms == 0 or not self.teachers_data: return []

        total_teacher_capacity_per_week = sum(max(0, sum(1 for day in DAYS_OF_WEEK for p_idx in range(num_p_day) if teacher.get('availability', {}).get(day, {}).get(p_idx, False)) - MIN_PREP_BLOCKS_PER_WEEK) for teacher in self.teachers_data)
        grid_capacity_per_week = self.params.get('num_concurrent_tracks_per_period', 1) * num_p_day * len(DAYS_OF_WEEK)
        effective_weekly_capacity_per_term = min(total_teacher_capacity_per_week, grid_capacity_per_week)

        p_dur_min = self.params.get('period_duration_minutes', 1)
        weeks_per_term = self.params.get('weeks_per_term', 18)
        if self.params.get('scheduling_model') == "Full Year": weeks_per_term = self.params.get('num_instructional_weeks', 36)

        def create_block_entry(block_name, subject_area, grade_level, term_num): # Local helper
            credits = TYPICAL_COURSE_CREDITS_FOR_ESTIMATE 
            course_mins = credits * CREDITS_TO_HOURS_PER_CREDIT * 60
            periods_year = math.ceil(course_mins / p_dur_min) if p_dur_min > 0 else 0
            periods_week = math.ceil(periods_year / weeks_per_term) if weeks_per_term > 0 else 0
            return {'name': block_name, 'credits': credits, 'grade_level': grade_level,
                    'subject_area': subject_area, 'term_assignment': term_num,
                    'periods_per_week_in_active_term': max(1, periods_week), 'parsed_constraints':[],
                    'scheduling_constraints_raw': "", '_is_suggestion': True}

        periods_used_by_term = defaultdict(int)
        
        for course_name, subject, grade in [('CALM 20', 'Other', 10), ('Physical Education 10', 'PE', 10)]:
             term = 1
             entry = create_block_entry(course_name, subject, grade, term)
             if not entry: continue
             periods_needed = entry['periods_per_week_in_active_term']
             if periods_used_by_term[term] + periods_needed <= effective_weekly_capacity_per_term:
                 suggested_grouped_courses.append(entry)
                 periods_used_by_term[term] += periods_needed

        cores_per_term = math.ceil(len(CORE_SUBJECTS_HS) / num_terms)
        assigned_blocks_by_grade_term = defaultdict(lambda: defaultdict(int))

        for term in range(1, num_terms + 1):
            for grade in [10, 11, 12]:
                shuffled_cores = random.sample(CORE_SUBJECTS_HS, len(CORE_SUBJECTS_HS))
                for subject in shuffled_cores:
                    if assigned_blocks_by_grade_term[grade][term] >= cores_per_term: break
                    if any(c['subject_area'] == subject and c['grade_level'] == grade for c in suggested_grouped_courses): continue
                    
                    block_name = f"{subject} {grade} Block"
                    entry = create_block_entry(block_name, subject, grade, term)
                    if not entry: continue
                    periods_needed = entry['periods_per_week_in_active_term']
                    if periods_used_by_term[term] + periods_needed <= effective_weekly_capacity_per_term:
                        suggested_grouped_courses.append(entry)
                        periods_used_by_term[term] += periods_needed
                        assigned_blocks_by_grade_term[grade][term] += 1
                        self._log_message(f"Suggested grouped block '{entry['name']}' ({periods_needed} p/wk in T{term})", "DEBUG")

        for term in range(1, num_terms + 1):
            remaining_capacity = effective_weekly_capacity_per_term - periods_used_by_term[term]
            if remaining_capacity > 0:
                num_cts_blocks = math.floor(remaining_capacity / PERIODS_PER_TYPICAL_OPTION_BLOCK)
                self._log_message(f"Term {term} has {remaining_capacity} p/wk remaining. Suggesting {num_cts_blocks} CTS block(s).", "INFO")
                for i in range(num_cts_blocks):
                    option_name = f"Suggested CTS Option Block (T{term}, #{i+1})"
                    option_entry = create_block_entry(option_name, "CTS", "Mixed", term)
                    if option_entry:
                        option_entry['periods_per_week_in_active_term'] = PERIODS_PER_TYPICAL_OPTION_BLOCK
                        suggested_grouped_courses.append(option_entry)
        return suggested_grouped_courses

    def suggest_new_courses_from_capacity(self, current_courses_list): # Renamed from _suggest_new_courses_based_on_capacity
        self._log_message("Calculating teacher capacity to suggest new courses.", "INFO")
        if not self.teachers_data: self._log_message("No teachers defined, cannot suggest new courses.", "WARN"); return []

        num_p_day = self.params.get('num_periods_per_day', 1)
        total_teacher_capacity_per_week = sum(max(0, sum(1 for day in DAYS_OF_WEEK for p_idx in range(num_p_day) if t.get('availability', {}).get(day, {}).get(p_idx, False)) - MIN_PREP_BLOCKS_PER_WEEK) for t in self.teachers_data)
        self._log_message(f"Total available teacher teaching periods/week (after prep): {total_teacher_capacity_per_week}", "DEBUG")

        scheduled_periods_per_week_by_term = defaultdict(int)
        for course in current_courses_list: scheduled_periods_per_week_by_term[course.get('term_assignment', 1)] += course.get('periods_per_week_in_active_term', 0)
        self._log_message(f"Scheduled periods/week by term: {dict(scheduled_periods_per_week_by_term)}", "DEBUG")

        newly_suggested_courses = []
        max_schedulable_slots_per_week = self.params.get('num_concurrent_tracks_per_period', 1) * num_p_day * len(DAYS_OF_WEEK)
        effective_capacity_per_week = min(total_teacher_capacity_per_week, max_schedulable_slots_per_week)
        
        all_cts_courses = [name for name in self.high_school_credits_db.keys() if any(kw.lower() in name.lower() for kw in CTS_KEYWORDS)]
        current_course_names = {c['name'] for c in current_courses_list}
        available_cts = [name for name in all_cts_courses if name not in current_course_names]
        random.shuffle(available_cts)

        p_dur_min = self.params.get('period_duration_minutes', 60)
        weeks_per_term = self.params.get('weeks_per_term', 18)
        if self.params.get('scheduling_model') == "Full Year": weeks_per_term = self.params.get('num_instructional_weeks', 36)

        for term in range(1, self.params.get('num_terms', 1) + 1):
            net_available_periods = effective_capacity_per_week - scheduled_periods_per_week_by_term[term]
            self._log_message(f"Term {term}: Effective Capacity={effective_capacity_per_week}, Scheduled={scheduled_periods_per_week_by_term[term]}, Net Available={net_available_periods}", "DEBUG")

            while net_available_periods >= 3 and available_cts: # Assuming min 3 periods for a viable course
                cts_name = available_cts.pop(0)
                credits = self.high_school_credits_db.get(cts_name, TYPICAL_COURSE_CREDITS_FOR_ESTIMATE)
                course_mins = credits * CREDITS_TO_HOURS_PER_CREDIT * 60
                periods_year = math.ceil(course_mins / p_dur_min) if p_dur_min > 0 else 0
                periods_week = math.ceil(periods_year / weeks_per_term) if weeks_per_term > 0 else 0
                periods_week = max(1, periods_week) # Ensure at least 1 period

                if periods_week > 0 and net_available_periods >= periods_week:
                    suggestion_entry = {
                        'name': cts_name, 'credits': credits, 'grade_level': "Mixed",
                        'subject_area': "CTS", 'term_assignment': term,
                        'periods_per_week_in_active_term': periods_week,
                        'scheduling_constraints_raw': "", 'parsed_constraints': [],
                        '_is_suggestion': True, '_is_one_credit_buffer_item': False
                    }
                    newly_suggested_courses.append(suggestion_entry)
                    net_available_periods -= periods_week
                    self._log_message(f"Suggesting new CTS course '{cts_name}' for Term {term}.", "INFO")
                elif periods_week > 0 : # Course is too big for remaining space, put back and stop
                    available_cts.insert(0, cts_name)
                    break 
                # If periods_week is 0, it's an invalid course, skip
        
        return newly_suggested_courses
    
    def generate_schedules(self, num_schedules_to_generate, max_total_attempts):
        self.current_run_log = [] # Reset log for this generation run
        self._log_message(f"--- Starting Schedule Generation Run (Target: {num_schedules_to_generate}, Max Attempts: {max_total_attempts}) ---", "INFO")
        self.generated_schedules_details = [] 
        generated_schedule_hashes = set()
        
        best_failed_schedule_data = {
            'schedule': None, 'log': [],
            'metrics': {'overall_completion_rate': 0.0, 'unmet_grade_slots_count': float('inf'), 'unmet_prep_teachers_count': float('inf')}
        }

        original_courses_data = copy.deepcopy(self.courses_data)
        original_cohort_constraints = copy.deepcopy(self.cohort_constraints)

        for attempt_num in range(max_total_attempts):
            if len(self.generated_schedules_details) >= num_schedules_to_generate: break
            
            self._log_message(f"--- Overall Schedule Gen Attempt {attempt_num + 1}/{max_total_attempts} ---", "DEBUG")
            
            # Create a separate log for this single attempt to avoid polluting the main log if it fails
            single_attempt_log_capture = []
            
            current_schedule, is_successful_attempt, attempt_metrics = self._generate_single_schedule_attempt(attempt_seed_modifier=attempt_num, attempt_log_list=single_attempt_log_capture)
            
            if current_schedule is None: # This indicates a fundamental issue, not just a failed placement
                self._log_message("CRITICAL ERROR: Fundamental input issues prevent scheduling. Check detailed logs from attempt.", "ERROR")
                self.current_run_log.extend(single_attempt_log_capture) # Add this attempt's log to main
                return False

            if is_successful_attempt:
                schedule_hash = hash(json.dumps(current_schedule, sort_keys=True, default=str))
                if schedule_hash not in generated_schedule_hashes:
                    s_id = len(self.generated_schedules_details) + 1
                    self.generated_schedules_details.append({'id': s_id, 'schedule': current_schedule, 'log': single_attempt_log_capture, 'metrics': attempt_metrics})
                    generated_schedule_hashes.add(schedule_hash)
                    self._log_message(f"SUCCESS: Found new distinct valid schedule (ID: {s_id}).", "INFO")
                else: 
                    self._log_message("INFO: Generated a schedule identical to a previous one. Trying again.", "DEBUG")
            else:
                self._log_message(f"INFO: Attempt {attempt_num + 1} did not yield a valid schedule. (Completion: {attempt_metrics.get('overall_completion_rate', 0)*100:.2f}%)", "DEBUG")
                current_is_better = (attempt_metrics['unmet_grade_slots_count'] < best_failed_schedule_data['metrics']['unmet_grade_slots_count']) or \
                                   (attempt_metrics['unmet_grade_slots_count'] == best_failed_schedule_data['metrics']['unmet_grade_slots_count'] and \
                                    attempt_metrics['unmet_prep_teachers_count'] < best_failed_schedule_data['metrics']['unmet_prep_teachers_count']) or \
                                   (attempt_metrics['unmet_grade_slots_count'] == best_failed_schedule_data['metrics']['unmet_grade_slots_count'] and \
                                    attempt_metrics['unmet_prep_teachers_count'] == best_failed_schedule_data['metrics']['unmet_prep_teachers_count'] and \
                                    attempt_metrics['overall_completion_rate'] > best_failed_schedule_data['metrics']['overall_completion_rate'])
                if current_is_better:
                    best_failed_schedule_data = {'schedule': current_schedule, 'log': single_attempt_log_capture, 'metrics': attempt_metrics}
                    self._log_message("This is the best failed attempt found so far.", "DEBUG")

        if not self.generated_schedules_details:
            self._log_message("Initial attempts failed. Checking for optimization potential.", "INFO")
            if self.params.get('school_type') == 'High School' and self._attempt_course_combination():
                self._log_message("--- RE-ATTEMPTING WITH COMBINED COURSES ---", "INFO")
                for attempt_num_opt in range(max_total_attempts): # Use a portion of attempts for optimized run
                    if len(self.generated_schedules_details) >= num_schedules_to_generate: break
                    self._log_message(f"--- Overall Schedule Gen Attempt {attempt_num_opt + 1}/{max_total_attempts} (OPTIMIZED RUN) ---", "DEBUG")
                    
                    single_attempt_log_capture_opt = []
                    current_schedule_opt, is_successful_attempt_opt, attempt_metrics_opt = \
                        self._generate_single_schedule_attempt(attempt_seed_modifier=attempt_num_opt + max_total_attempts, attempt_log_list=single_attempt_log_capture_opt) # Different seed base
                    
                    if current_schedule_opt is None: self._log_message("CRITICAL ERROR during optimized run.", "ERROR"); break

                    if is_successful_attempt_opt:
                        schedule_hash_opt = hash(json.dumps(current_schedule_opt, sort_keys=True, default=str))
                        if schedule_hash_opt not in generated_schedule_hashes:
                            s_id_opt = len(self.generated_schedules_details) + 1
                            self.generated_schedules_details.append({'id': f"{s_id_opt}-Optimized", 'schedule': current_schedule_opt, 'log': single_attempt_log_capture_opt, 'metrics': attempt_metrics_opt})
                            generated_schedule_hashes.add(schedule_hash_opt)
                            self._log_message(f"SUCCESS: Found new distinct valid schedule (ID: {s_id_opt}-Optimized).", "INFO")
                        # else: self._log_message("INFO: Optimized run generated a schedule identical to a previous one.", "DEBUG") # Less verbose for dupes in optimized
                    else:
                        # Update best_failed_schedule_data if this optimized failure is better
                        current_is_better_opt = (attempt_metrics_opt['unmet_grade_slots_count'] < best_failed_schedule_data['metrics']['unmet_grade_slots_count']) or \
                                   (attempt_metrics_opt['unmet_grade_slots_count'] == best_failed_schedule_data['metrics']['unmet_grade_slots_count'] and \
                                    attempt_metrics_opt['unmet_prep_teachers_count'] < best_failed_schedule_data['metrics']['unmet_prep_teachers_count']) or \
                                   (attempt_metrics_opt['unmet_grade_slots_count'] == best_failed_schedule_data['metrics']['unmet_grade_slots_count'] and \
                                    attempt_metrics_opt['unmet_prep_teachers_count'] == best_failed_schedule_data['metrics']['unmet_prep_teachers_count'] and \
                                    attempt_metrics_opt['overall_completion_rate'] > best_failed_schedule_data['metrics']['overall_completion_rate'])
                        if current_is_better_opt:
                            best_failed_schedule_data = {'schedule': current_schedule_opt, 'log': single_attempt_log_capture_opt, 'metrics': attempt_metrics_opt}
                            self._log_message("This (optimized) is the new best failed attempt found so far.", "DEBUG")
            
            self.courses_data = original_courses_data # Restore original courses
            self.cohort_constraints = original_cohort_constraints

        if not self.generated_schedules_details:
            self._log_message("FINAL: Could not generate any valid schedules, even after optimization attempts.", "ERROR")
            if best_failed_schedule_data['schedule']:
                best_failed_schedule_data['id'] = "Best_Failed_Attempt"
                self.generated_schedules_details.append(best_failed_schedule_data) # Add the best failure
            return False
        
        self._log_message(f"SUCCESS: Generated {len(self.generated_schedules_details)} valid schedule(s).", "INFO")
        return True

    def _generate_single_schedule_attempt(self, attempt_seed_modifier=0, attempt_log_list=None):
        # If no separate log list is provided, log to the main engine log
        # This allows detailed logging of a single attempt if needed, without polluting main log on success
        log_fn = lambda msg, level="INFO": (attempt_log_list.append(f"[{level}] {msg}") if attempt_log_list is not None else self._log_message(msg, level))

        log_fn(f"--- Attempting Schedule Generation (Seed Mod: {attempt_seed_modifier}, Min Prep: {MIN_PREP_BLOCKS_PER_WEEK}) ---", "DEBUG")
        num_p_day = self.params.get('num_periods_per_day',1)
        if not isinstance(num_p_day, int) or num_p_day <= 0: num_p_day = 1 # Safety
        num_terms = self.params.get('num_terms',1)
        num_tracks = self.params.get('num_concurrent_tracks_per_period', 1)
        is_hs = self.params.get('school_type') == 'High School'
        
        current_schedule = {t: {d: [[None]*num_tracks for _ in range(num_p_day)] for d in DAYS_OF_WEEK} for t in range(1, num_terms + 1)}
        
        items_by_term = defaultdict(list)
        source_data = self.subjects_data if not is_hs else self.courses_data
        
        if not source_data: 
            log_fn("No subjects/courses defined. Cannot generate schedule.", "ERROR")
            return None, False, {'overall_completion_rate': 0, 'unmet_grade_slots_count': float('inf'), 'unmet_prep_teachers_count': float('inf')}
        if not self.teachers_data: 
            log_fn("No teachers defined. Cannot generate schedule.", "ERROR")
            return None, False, {'overall_completion_rate': 0, 'unmet_grade_slots_count': float('inf'), 'unmet_prep_teachers_count': float('inf')}

        for item_data_orig in source_data:
            item_data = copy.deepcopy(item_data_orig) # Work with a copy
            if item_data is None : continue
            term_num_item = item_data.get('term_assignment', 1)
            terms_to_sched_in = list(range(1, num_terms + 1)) if not is_hs and num_terms > 1 else [term_num_item]
            for term_actual in terms_to_sched_in:
                if 1 <= term_actual <= num_terms:
                    items_by_term[term_actual].append({
                        **item_data, 
                        'teacher': None, 
                        'periods_to_schedule_this_week': item_data.get('periods_per_week', item_data.get('periods_per_week_in_active_term', 0)),
                        'constraints': item_data.get('parsed_constraints', []), 
                        'type': 'subject' if not is_hs else 'course',
                        'placed_this_term_count': 0, 
                        'is_cts_course': "cts" in item_data.get('subject_area','').lower() if is_hs else False,
                    })

        teacher_max_teaching_this_week = {}
        for teacher in self.teachers_data:
            teacher_name = teacher['name']; total_avail_slots = 0
            for day_k in DAYS_OF_WEEK:
                for period_k in range(num_p_day):
                    if teacher.get('availability', {}).get(day_k, {}).get(period_k, False): total_avail_slots += 1
            max_t = total_avail_slots - MIN_PREP_BLOCKS_PER_WEEK
            teacher_max_teaching_this_week[teacher_name] = max_t
            if max_t < 0: log_fn(f"WARN Teacher {teacher_name}: {total_avail_slots} avail, < {MIN_PREP_BLOCKS_PER_WEEK} prep. Max teach {max_t}. Cannot teach.", "WARN")
        
        is_overall_successful_attempt = True # Success of the entire multi-term schedule
        attempt_metrics = {'overall_completion_rate': 0.0, 'unmet_grade_slots_count': 0, 'unmet_prep_teachers_count': 0}
        all_terms_overall_completion_rates_for_avg = [] # For averaging completion

        # --- Local helper for grade coverage, used per term ---
        def update_grade_coverage_local(item_obj, day_name, p_idx, grade_coverage_dict_local):
            if not is_hs: return
            item_grade = item_obj.get('grade_level')
            grades_to_update = []
            if item_grade == "Mixed": grades_to_update = GRADES_REQUIRING_FULL_SCHEDULE
            elif isinstance(item_grade, int) and item_grade in GRADES_REQUIRING_FULL_SCHEDULE: grades_to_update = [item_grade]
            
            for grade_val in grades_to_update:
                if grade_val in grade_coverage_dict_local:
                    grade_coverage_dict_local[grade_val][day_name][p_idx] = True
        
        # --- Loop through each term ---
        for term_idx in range(1, num_terms + 1):
            log_fn(f"--- Processing Term {term_idx} ---", "DEBUG")
            current_term_course_list_for_scheduling = items_by_term.get(term_idx, [])
            if not current_term_course_list_for_scheduling:
                log_fn(f"No courses/subjects defined for Term {term_idx}. Skipping.", "INFO")
                all_terms_overall_completion_rates_for_avg.append(1.0) # 100% completion for an empty term
                continue

            teacher_busy_this_term = defaultdict(set)
            item_scheduled_on_day_this_term = defaultdict(set)
            item_placements_this_term = defaultdict(list) # Track (day, period) for same-slot logic
            teacher_teaching_periods_this_week_for_term = defaultdict(int)
            
            must_assign_items, flexible_items_all = [], []
            for item_sort in current_term_course_list_for_scheduling: 
                (must_assign_items if any(c.get('type') == 'ASSIGN' for c in item_sort.get('constraints',[])) else flexible_items_all).append(item_sort)
            
            grade_coverage_this_term = {g: {d: [False] * num_p_day for d in DAYS_OF_WEEK} for g in GRADES_REQUIRING_FULL_SCHEDULE}
            
            # --- Process MUST ASSIGN items first ---
            for item in must_assign_items:
                item_name, item_subj_area = item['name'], item.get('subject_area')
                assign_constr = [c for c in item.get('constraints',[]) if c.get('type') == 'ASSIGN']
                num_assign_slots = len(assign_constr)
                
                if not item_subj_area: 
                    log_fn(f"CRIT (Term {term_idx}): ASSIGN item '{item_name}' missing subject. Scheduling FAILED.", "ERROR")
                    return current_schedule, False, {'overall_completion_rate': 0, 'unmet_grade_slots_count': float('inf'), 'unmet_prep_teachers_count': float('inf')}
                
                teacher_for_all = None
                potential_teachers_for_assign = [t for t in self.teachers_data if self._is_teacher_qualified(t, item_subj_area)]
                random.shuffle(potential_teachers_for_assign) 
                for t_obj_cand in potential_teachers_for_assign:
                    cand_name = t_obj_cand['name']
                    if teacher_teaching_periods_this_week_for_term.get(cand_name,0) + num_assign_slots > teacher_max_teaching_this_week.get(cand_name, -1): continue
                    all_specific_slots_available = True
                    for slot_c in assign_constr:
                        day_c, period_c = slot_c['day'], slot_c['period']
                        if not t_obj_cand.get('availability',{}).get(day_c,{}).get(period_c,False) or (day_c,period_c) in teacher_busy_this_term.get(cand_name,set()):
                            all_specific_slots_available = False; break
                    if all_specific_slots_available: teacher_for_all = cand_name; break
                
                if not teacher_for_all: 
                    log_fn(f"CRIT (Term {term_idx}): No teacher for ASSIGN slots of '{item_name}'. Scheduling FAILED.", "ERROR")
                    return current_schedule, False, {'overall_completion_rate': 0, 'unmet_grade_slots_count': float('inf'), 'unmet_prep_teachers_count': float('inf')}
                
                item['teacher'] = teacher_for_all # Assign teacher to the item
                slots_placed_ok_count_for_assign = 0
                for slot_c in assign_constr:
                    day_c, period_c = slot_c['day'], slot_c['period']
                    if any((nc.get('day')==day_c or nc.get('day') is None) and nc.get('period')==period_c for nc in item.get('constraints',[]) if nc.get('type')=='NOT'): 
                        log_fn(f"CRIT (Term {term_idx}): ASSIGN slot {day_c}-P{period_c+1} for '{item_name}' conflicts NOT constraint. Scheduling FAILED.", "ERROR")
                        return current_schedule, False, {'overall_completion_rate': 0, 'unmet_grade_slots_count': float('inf'), 'unmet_prep_teachers_count': float('inf')}
                    
                    track_found_assign = False
                    for track_idx_assign in range(num_tracks):
                        if current_schedule[term_idx][day_c][period_c][track_idx_assign] is None:
                            if self._check_cohort_clash_in_slot(item_name, term_idx, day_c, period_c, current_schedule): continue
                            current_schedule[term_idx][day_c][period_c][track_idx_assign] = (item_name, teacher_for_all)
                            update_grade_coverage_local(item, day_c, period_c, grade_coverage_this_term) 
                            track_found_assign = True; slots_placed_ok_count_for_assign +=1
                            # Add to busy sets and placements
                            teacher_busy_this_term[teacher_for_all].add((day_c, period_c))
                            item_scheduled_on_day_this_term[item_name].add(day_c)
                            item_placements_this_term[item_name].append((day_c, period_c))
                            break
                    
                    if not track_found_assign: 
                        log_fn(f"CRIT (Term {term_idx}): No track in ASSIGN slot {day_c}-P{period_c+1} for '{item_name}'. Scheduling FAILED.", "ERROR")
                        return current_schedule, False, {'overall_completion_rate': 0, 'unmet_grade_slots_count': float('inf'), 'unmet_prep_teachers_count': float('inf')}
                
                item['placed_this_term_count'] = slots_placed_ok_count_for_assign
                teacher_teaching_periods_this_week_for_term[teacher_for_all] += slots_placed_ok_count_for_assign # Use actual placed count
                log_fn(f"ASSIGNED (Term {term_idx}): '{item_name}' (T:{teacher_for_all}) to {slots_placed_ok_count_for_assign} slots. Load: {teacher_teaching_periods_this_week_for_term[teacher_for_all]}/{teacher_max_teaching_this_week.get(teacher_for_all, 'N/A')}", "DEBUG")
            
            # --- Process FLEXIBLE items ---
            flexible_items_processed = sorted(flexible_items_all, key=lambda x: (x.get('periods_to_schedule_this_week',0), len(x.get('constraints',[]))), reverse=True)
            if attempt_seed_modifier > 0 : random.seed(datetime.datetime.now().microsecond + attempt_seed_modifier + term_idx); random.shuffle(flexible_items_processed)
            
            for item in flexible_items_processed:
                item_name, item_subj_area = item['name'], item.get('subject_area')
                not_constr = [c for c in item.get('constraints',[]) if c.get('type')=='NOT']
                periods_to_place = item.get('periods_to_schedule_this_week',0)
                item_teacher = item.get('teacher') # Might be pre-assigned if it was also a must_assign (unlikely but possible)
                
                if not item_subj_area: log_fn(f"WARN (Term {term_idx}): Flex item '{item_name}' missing subject. Skipping.", "WARN"); continue
                if periods_to_place == 0: item['placed_this_term_count'] = 0; continue # Already handled or 0 periods
                
                num_remaining_to_place_for_flex = periods_to_place - item.get('placed_this_term_count', 0)
                if num_remaining_to_place_for_flex <= 0: continue
                
                for _ in range(num_remaining_to_place_for_flex):
                    candidate_slots = []
                    
                    # --- Logic to enforce same-time-slot preference for flexible items ---
                    periods_to_check_for_flex = range(num_p_day)
                    if self.params.get('force_same_time_slot') and item_name in item_placements_this_term and item_placements_this_term[item_name]:
                        home_period = item_placements_this_term[item_name][0][1] # Get period from first placement
                        periods_to_check_for_flex = [home_period]
                    
                    for day_name_flex in DAYS_OF_WEEK:
                        if not self.params.get('multiple_times_same_day', True) and day_name_flex in item_scheduled_on_day_this_term.get(item_name, set()): continue
                        
                        for p_idx_flex in periods_to_check_for_flex: 
                            if any((nc.get('day') == day_name_flex or nc.get('day') is None) and nc.get('period') == p_idx_flex for nc in not_constr): continue
                            if any(current_schedule[term_idx][day_name_flex][p_idx_flex][t] is None for t in range(num_tracks)): # Check if any track is empty
                                if self._check_cohort_clash_in_slot(item_name, term_idx, day_name_flex, p_idx_flex, current_schedule): continue
                                if self._find_qualified_teacher(item_subj_area, day_name_flex, p_idx_flex, teacher_busy_this_term, teacher_teaching_periods_this_week_for_term, teacher_max_teaching_this_week, item_teacher) is None: continue
                                
                                score = 0 # Score for empty grade slots
                                if is_hs:
                                    item_grade_level = item.get('grade_level')
                                    grades_to_update_score = []
                                    if item_grade_level == "Mixed": grades_to_update_score = GRADES_REQUIRING_FULL_SCHEDULE
                                    elif isinstance(item_grade_level, int) and item_grade_level in GRADES_REQUIRING_FULL_SCHEDULE: grades_to_update_score = [item_grade_level]
                                    for g_score in grades_to_update_score:
                                        if g_score in grade_coverage_this_term and not grade_coverage_this_term[g_score][day_name_flex][p_idx_flex]: score += 1
                                candidate_slots.append({'day': day_name_flex, 'period': p_idx_flex, 'score': score})
                    
                    if not candidate_slots:
                        log_fn(f"WARN (Term {term_idx}): No valid slots for instance of '{item_name}'. Placed {item.get('placed_this_term_count',0)}/{periods_to_place}.", "WARN")
                        break 
                    
                    random.shuffle(candidate_slots) 
                    candidate_slots.sort(key=lambda x: x['score'], reverse=True) # Prioritize slots that fill grade gaps
                    
                    slot_found_this_instance = False
                    for slot_info in candidate_slots:
                        day_flex, p_idx_flex = slot_info['day'], slot_info['period']
                        teacher_for_slot = self._find_qualified_teacher(item_subj_area, day_flex, p_idx_flex, teacher_busy_this_term, teacher_teaching_periods_this_week_for_term, teacher_max_teaching_this_week, item_teacher)
                        
                        if teacher_for_slot:
                            if not item_teacher: item_teacher = teacher_for_slot; item['teacher'] = item_teacher # Lock in teacher
                            
                            if item_teacher == teacher_for_slot: # Ensure same teacher is used for all instances of this course in this term
                                for track_idx_flex in range(num_tracks):
                                    if current_schedule[term_idx][day_flex][p_idx_flex][track_idx_flex] is None:
                                        current_schedule[term_idx][day_flex][p_idx_flex][track_idx_flex] = (item_name, item_teacher)
                                        item_placements_this_term[item_name].append((day_flex, p_idx_flex))
                                        teacher_busy_this_term[item_teacher].add((day_flex, p_idx_flex))
                                        item_scheduled_on_day_this_term[item_name].add(day_flex)
                                        teacher_teaching_periods_this_week_for_term[item_teacher] += 1
                                        item['placed_this_term_count'] += 1
                                        update_grade_coverage_local(item, day_flex, p_idx_flex, grade_coverage_this_term) 
                                        slot_found_this_instance = True
                                        break 
                            if slot_found_this_instance: break
                
                final_placed_count_flex = item.get('placed_this_term_count', 0)
                if final_placed_count_flex == periods_to_place: log_fn(f"SCHED (Term {term_idx}): Flex item '{item_name}' (T:{item_teacher or 'Unassigned!'}) all {final_placed_count_flex} pds.", "DEBUG")
                elif final_placed_count_flex > 0 : log_fn(f"PARTIAL (Term {term_idx}): '{item_name}' (T:{item_teacher or 'Unassigned!'}) {final_placed_count_flex}/{periods_to_place}.", "WARN")
            
            # --- Verification for the Term ---
            total_periods_needed_term = sum(it.get('periods_to_schedule_this_week',0) for it in current_term_course_list_for_scheduling); 
            total_periods_placed_term = sum(it.get('placed_this_term_count',0) for it in current_term_course_list_for_scheduling)
            
            term_completion_rate = 0.0
            if total_periods_needed_term > 0:
                term_completion_rate = total_periods_placed_term / total_periods_needed_term
                log_fn(f"Term {term_idx} Completion: {total_periods_placed_term}/{total_periods_needed_term} ({term_completion_rate*100:.2f}%).", "INFO")
                if term_completion_rate < MIN_ACCEPTABLE_SCHEDULE_COMPLETION_RATE:
                    log_fn(f"ERROR (Term {term_idx}): Completion ({term_completion_rate*100:.2f}%) < min {MIN_ACCEPTABLE_SCHEDULE_COMPLETION_RATE*100}%. Invalidating attempt.", "ERROR")
                    is_overall_successful_attempt = False 
            elif not current_term_course_list_for_scheduling: log_fn(f"INFO (Term {term_idx}): No items to schedule.", "INFO"); term_completion_rate = 1.0 # Empty term is 100% complete
            else: log_fn(f"INFO (Term {term_idx}): All items have 0 periods needed.", "INFO"); term_completion_rate = 1.0
            all_terms_overall_completion_rates_for_avg.append(term_completion_rate)

            # Prep block verification for this term
            for teacher_check in self.teachers_data:
                name_check = teacher_check['name']
                actual_teaching_this_term_val = teacher_teaching_periods_this_week_for_term.get(name_check, 0)
                total_personal_avail_this_config = sum(1 for d_avail in DAYS_OF_WEEK for p_avail in range(num_p_day) if teacher_check.get('availability',{}).get(d_avail,{}).get(p_avail, False))
                actual_prep = total_personal_avail_this_config - actual_teaching_this_term_val
                
                if teacher_max_teaching_this_week.get(name_check, -1) < 0 and actual_teaching_this_term_val > 0 : # Should not have taught
                    log_fn(f"ERROR (Term {term_idx}): Teacher {name_check} was unscheduleable but taught. Invalidating attempt.", "ERROR")
                    is_overall_successful_attempt = False; attempt_metrics['unmet_prep_teachers_count'] += 1
                elif actual_prep < MIN_PREP_BLOCKS_PER_WEEK: 
                    log_fn(f"ERROR (Term {term_idx}): Teacher {name_check} has {actual_prep} prep, < {MIN_PREP_BLOCKS_PER_WEEK}. Invalidating attempt.", "ERROR")
                    is_overall_successful_attempt = False; attempt_metrics['unmet_prep_teachers_count'] += 1
            log_fn(f"Term {term_idx} prep blocks verified.", "DEBUG")

            # HS Grade full schedule verification for this term
            if is_hs:
                unmet_slots_for_all_grades_this_term = 0
                for grade_to_check in GRADES_REQUIRING_FULL_SCHEDULE:
                    for day_check_fill in DAYS_OF_WEEK:
                        for period_check_fill in range(num_p_day):
                            if not grade_coverage_this_term.get(grade_to_check, {}).get(day_check_fill, [])[period_check_fill]:
                                log_fn(f"ERROR (Term {term_idx}): Grade {grade_to_check} no class {day_check_fill} P{period_check_fill+1}. Invalidating attempt.", "ERROR")
                                unmet_slots_for_all_grades_this_term += 1
                if unmet_slots_for_all_grades_this_term > 0:
                    is_overall_successful_attempt = False
                    attempt_metrics['unmet_grade_slots_count'] += unmet_slots_for_all_grades_this_term
                log_fn(f"Term {term_idx}: Full block schedule verified for Grades {GRADES_REQUIRING_FULL_SCHEDULE}.", "DEBUG")
            log_fn(f"Term {term_idx} scheduling completed and verified.", "DEBUG")
        
        # --- Final overall metrics for the multi-term schedule attempt ---
        if all_terms_overall_completion_rates_for_avg:
            attempt_metrics['overall_completion_rate'] = sum(all_terms_overall_completion_rates_for_avg) / len(all_terms_overall_completion_rates_for_avg)
        
        if is_overall_successful_attempt:
            log_fn("Full Schedule Generation Attempt Finished Successfully.", "INFO")
        else:
            log_fn("Full Schedule Generation Attempt Failed Validation (see errors above).", "INFO")

        return current_schedule, is_overall_successful_attempt, attempt_metrics
    
    def _is_teacher_qualified(self, teacher_obj, subject_area):
        if subject_area == "Other": return True 
        return subject_area in teacher_obj.get('qualifications', [])

    def _find_qualified_teacher(self, subject_area, day_name, period_idx, teacher_busy_this_term, teacher_teaching_periods_this_week, teacher_max_teaching_this_week, existing_teacher_for_offering=None):
        num_p_day = self.params.get('num_periods_per_day', 1) # Ensure this is available
        if not isinstance(num_p_day, int) or num_p_day <= 0: num_p_day = 1

        if existing_teacher_for_offering:
            teacher_obj = next((t for t in self.teachers_data if t['name'] == existing_teacher_for_offering), None)
            if teacher_obj and self._is_teacher_qualified(teacher_obj, subject_area) and \
               teacher_obj.get('availability', {}).get(day_name, {}).get(period_idx, False) and \
               (day_name, period_idx) not in teacher_busy_this_term.get(existing_teacher_for_offering, set()) and \
               teacher_teaching_periods_this_week.get(existing_teacher_for_offering, 0) < teacher_max_teaching_this_week.get(existing_teacher_for_offering, float('-inf')):
                return existing_teacher_for_offering
            return None # Preferred teacher cannot take it
        
        shuffled_teachers = random.sample(self.teachers_data, len(self.teachers_data))
        candidate_teachers = []
        for teacher in shuffled_teachers:
            teacher_name = teacher['name']
            if teacher_max_teaching_this_week.get(teacher_name, -1) < 0: continue # Teacher cannot teach due to prep or misconfiguration
            if self._is_teacher_qualified(teacher, subject_area) and \
               teacher.get('availability', {}).get(day_name, {}).get(period_idx, False) and \
               (day_name, period_idx) not in teacher_busy_this_term.get(teacher_name, set()) and \
               teacher_teaching_periods_this_week.get(teacher_name, 0) < teacher_max_teaching_this_week.get(teacher_name, 0): # Check against max load
                candidate_teachers.append(teacher_name)
        return random.choice(candidate_teachers) if candidate_teachers else None

    def _check_cohort_clash_in_slot(self, item_name_to_schedule, term_idx, day_name, period_idx, current_schedule):
        num_tracks = self.params.get('num_concurrent_tracks_per_period', 1)
        base_item_name = item_name_to_schedule.split(' (')[0].strip() # Get base name for blocks
        for track_idx_check in range(num_tracks):
            existing_item_tuple = current_schedule[term_idx][day_name][period_idx][track_idx_check]
            if existing_item_tuple:
                existing_base_name = existing_item_tuple[0].split(' (')[0].strip()
                for clash_group in self.cohort_constraints:
                    # Ensure clash_group is a list/tuple before checking 'in'
                    if isinstance(clash_group, (list, tuple)) and base_item_name in clash_group and existing_base_name in clash_group:
                        # self._log_message(f"COHORT CLASH: '{item_name_to_schedule}' vs '{existing_item_tuple[0]}' in T{term_idx}-{day_name}-P{period_idx+1}", "TRACE") # Logged by calling function if needed
                        return True
        return False

    def _attempt_course_combination(self):
        if self.params.get('school_type') != 'High School': return False

        courses_modified = False
        courses_to_add = []
        course_names_to_remove = set()
        remap_for_cohorts = {} # {old_name: new_name}

        for course1_name, course2_name in COMBINABLE_PAIRS:
            course1_obj = next((c for c in self.courses_data if c['name'] == course1_name and c['name'] not in course_names_to_remove), None)
            course2_obj = next((c for c in self.courses_data if c['name'] == course2_name and c['name'] not in course_names_to_remove), None)

            if not course1_obj or not course2_obj: continue

            if course1_obj.get('term_assignment') != course2_obj.get('term_assignment'):
                self._log_message(f"Cannot combine '{course1_name}' and '{course2_name}': different terms.", "WARN")
                continue
            if any(con['type'] == 'ASSIGN' for con in course1_obj.get('parsed_constraints', [])) or \
               any(con['type'] == 'ASSIGN' for con in course2_obj.get('parsed_constraints', [])):
                self._log_message(f"Cannot combine '{course1_name}' and '{course2_name}': 'ASSIGN' constraint.", "WARN")
                continue

            periods_week = max(course1_obj['periods_per_week_in_active_term'], course2_obj['periods_per_week_in_active_term'])
            credits = max(course1_obj['credits'], course2_obj['credits'])
            new_name = f"{course1_name} / {course2_name}"
            self._log_message(f"OPTIMIZING: Combining '{course1_name}' and '{course2_name}' into '{new_name}'.", "INFO")

            merged_constraints_raw = "; ".join(filter(None, [course1_obj.get('scheduling_constraints_raw'), course2_obj.get('scheduling_constraints_raw')]))
            num_p_day_for_parse = self.params.get('num_periods_per_day', 1)
            parsed_constraints = parse_scheduling_constraint(merged_constraints_raw, num_p_day_for_parse)
            
            weeks_per_term_calc = self.params.get('weeks_per_term', 18)
            if self.params.get('scheduling_model') == "Full Year": weeks_per_term_calc = self.params.get('num_instructional_weeks', 36)

            combined_course = {
                'name': new_name, 'credits': credits, 'grade_level': "Mixed", # Combined courses are often mixed
                'assigned_teacher_name': None, 'subject_area': course1_obj['subject_area'], # Assume same subject area
                'periods_per_year_total_instances': periods_week * weeks_per_term_calc, # Recalculate based on merged periods/week
                'periods_per_week_in_active_term': periods_week,
                'scheduling_constraints_raw': merged_constraints_raw,
                'parsed_constraints': parsed_constraints,
                'term_assignment': course1_obj['term_assignment'],
                '_is_one_credit_buffer_item': False # Combined courses are not 1-credit buffers
            }
            courses_to_add.append(combined_course)
            course_names_to_remove.add(course1_name)
            course_names_to_remove.add(course2_name)
            remap_for_cohorts[course1_name] = new_name
            remap_for_cohorts[course2_name] = new_name
            courses_modified = True

        if courses_modified:
            self.courses_data = [c for c in self.courses_data if c['name'] not in course_names_to_remove]
            self.courses_data.extend(courses_to_add)
            
            new_cohort_constraints = []
            for group in self.cohort_constraints:
                new_group = list(set(remap_for_cohorts.get(name, name) for name in group)) # Use set to handle duplicates if both courses in a pair were in the same constraint
                if len(new_group) > 1: # Only keep constraint if it still has at least 2 distinct items
                    new_cohort_constraints.append(new_group)
            self.cohort_constraints = new_cohort_constraints
            self._log_message(f"Updated cohort constraints after combination: {len(self.cohort_constraints)} remaining.", "DEBUG")
        
        return courses_modified
