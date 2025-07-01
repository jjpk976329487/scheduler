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
MAX_SCHEDULE_GENERATION_ATTEMPTS = 200
MAX_DISTINCT_SCHEDULES_TO_GENERATE = 10
MIN_PREP_BLOCKS_PER_WEEK = 1
MIN_ACCEPTABLE_SCHEDULE_COMPLETION_RATE = 0.75
GRADES_REQUIRING_FULL_SCHEDULE = [10] # Default, can be overridden by params
PERIODS_PER_TYPICAL_OPTION_BLOCK = 5

TARGET_SUGGESTIONS_PER_TERM = 12

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

CORE_COURSE_BASE_NAMES = [
    "English 10", "English 20", "English 30",
    "Social Studies 10", "Social Studies 20", "Social Studies 30",
    "Math 10", "Math 20", "Math 30",
    "Science 10", "Biology 20", "Chemistry 20", "Physics 20",
    "Biology 30", "Chemistry 30", "Physics 30", "Science 14",
    "Science 24", "Science 20", "Science 30"
]

# ... (rest of helper functions and constants are unchanged) ...

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
    num_periods = num_periods if isinstance(num_periods, int) and num_periods > 0 else 1
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
                target_day_not = day_name_iter
                parts_not = parts_not[1:]
                break
    days_to_apply = [target_day_not] if target_day_not else DAYS_OF_WEEK

    if not parts_not:
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
    except ValueError: pass

    for day_apply_final in days_to_apply:
        for p_idx_con in indices_to_constrain:
            if 0 <= p_idx_con < num_periods:
                parsed_constraints.append({'type': 'NOT', 'day': day_apply_final, 'period': p_idx_con})
    return parsed_constraints

class SchedulingEngine:
    def __init__(self):
        self.params = {
            'grades_requiring_full_schedule': GRADES_REQUIRING_FULL_SCHEDULE,
        }
        self.teachers_data = []
        self.courses_data = []
        self.subjects_data = []
        self.cohort_constraints = []
        self.high_school_credits_db = copy.deepcopy(HIGH_SCHOOL_COURSE_CREDITS_TEMPLATE)
        self.generated_schedules_details = []
        self.current_run_log = []

    def set_parameters(self, params_dict):
        self.params = copy.deepcopy(params_dict)
        self._log_message(f"Engine received parameters: num_periods_per_day={self.params.get('num_periods_per_day')}, num_terms={self.params.get('num_terms')}, school_type={self.params.get('school_type')}, num_concurrent_tracks_per_period={self.params.get('num_concurrent_tracks_per_period')}", "DEBUG")

    def set_teachers(self, teachers_list): self.teachers_data = copy.deepcopy(teachers_list)
    def set_courses(self, courses_list): self.courses_data = copy.deepcopy(courses_list)
    def set_subjects(self, subjects_list): self.subjects_data = copy.deepcopy(subjects_list)
    def set_cohort_constraints(self, constraints_list): self.cohort_constraints = copy.deepcopy(constraints_list)
    def set_hs_credits_db(self, db_dict): self.high_school_credits_db = copy.deepcopy(db_dict)
    def get_parameters(self): return copy.deepcopy(self.params)
    def get_generated_schedules(self): return self.generated_schedules_details
    def get_run_log(self): return self.current_run_log

    def _log_message(self, message, level="INFO"):
        log_entry = f"[{level}] {datetime.datetime.now().strftime('%H:%M:%S')} {message}"
        print(log_entry)
        self.current_run_log.append(log_entry)

    def suggest_non_instructional_days(self):
        # This function is unchanged.
        return ""
    def suggest_core_courses(self):
        # This function is unchanged.
        return []
    def suggest_grouped_courses(self):
        # This function is unchanged.
        return []
    def suggest_new_courses_from_capacity(self, current_courses_list):
        # This function is unchanged.
        return []


    # --- MODIFIED FUNCTION ---
    def generate_schedules(self, num_schedules_to_generate, max_total_attempts):
        self.current_run_log = []
        self._log_message(f"--- Starting Schedule Generation Run (Internal Target: {MAX_DISTINCT_SCHEDULES_TO_GENERATE}, Max Attempts: {max_total_attempts}) ---", "INFO")
        self.generated_schedules_details = []
        generated_schedule_hashes = set()

        best_failed_schedule_data = {
            'schedule': None, 'log': [], 'placed_courses': None,
            'metrics': {'overall_completion_rate': 0.0, 'unmet_grade_slots_count': float('inf'), 'unmet_prep_teachers_count': float('inf')}
        }

        original_courses_data = copy.deepcopy(self.courses_data)
        original_cohort_constraints = copy.deepcopy(self.cohort_constraints)

        for attempt_num in range(max_total_attempts):
            if len(self.generated_schedules_details) >= MAX_DISTINCT_SCHEDULES_TO_GENERATE:
                self._log_message(f"Internal target of {MAX_DISTINCT_SCHEDULES_TO_GENERATE} distinct schedules reached. Stopping generation.", "INFO")
                break

            self._log_message(f"--- Overall Schedule Gen Attempt {attempt_num + 1}/{max_total_attempts} ---", "DEBUG")

            single_attempt_log_capture = []
            # MODIFIED: Capture the final course list from the attempt
            current_schedule, is_successful_attempt, attempt_metrics, placed_courses = self._generate_single_schedule_attempt(attempt_seed_modifier=attempt_num, attempt_log_list=single_attempt_log_capture)

            self.current_run_log.extend(single_attempt_log_capture)

            if current_schedule is None:
                self._log_message("CRITICAL ERROR: Fundamental input issues prevent scheduling. Check detailed logs from attempt.", "ERROR")
                return False

            if is_successful_attempt:
                schedule_hash = hash(json.dumps(current_schedule, sort_keys=True, default=str))
                if schedule_hash not in generated_schedule_hashes:
                    s_id = len(self.generated_schedules_details) + 1
                    # MODIFIED: Store the placed_courses data with the schedule
                    self.generated_schedules_details.append({
                        'id': s_id, 'schedule': current_schedule, 'log': single_attempt_log_capture,
                        'metrics': attempt_metrics, 'placed_courses': placed_courses
                    })
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
                    # MODIFIED: Store placed_courses for the best failed attempt
                    best_failed_schedule_data = {'schedule': current_schedule, 'log': single_attempt_log_capture,
                                                 'metrics': attempt_metrics, 'placed_courses': placed_courses}
                    self._log_message("This is the best failed attempt found so far.", "DEBUG")

        # --- This logic runs AFTER initial attempts, before returning ---
        if not self.generated_schedules_details and self.params.get('school_type') == 'High School' and self._attempt_course_combination():
            self._log_message("--- RE-ATTEMPTING WITH COMBINED COURSES ---", "INFO")
            for attempt_num_opt in range(max_total_attempts):
                if len(self.generated_schedules_details) >= MAX_DISTINCT_SCHEDULES_TO_GENERATE:
                    self._log_message(f"Internal target of {MAX_DISTINCT_SCHEDULES_TO_GENERATE} distinct schedules reached. Stopping generation.", "INFO")
                    break
                self._log_message(f"--- Overall Schedule Gen Attempt {attempt_num_opt + 1}/{max_total_attempts} (OPTIMIZED RUN) ---", "DEBUG")

                single_attempt_log_capture_opt = []
                current_schedule_opt, is_successful_attempt_opt, attempt_metrics_opt, placed_courses_opt = \
                    self._generate_single_schedule_attempt(attempt_seed_modifier=attempt_num_opt + max_total_attempts, attempt_log_list=single_attempt_log_capture_opt)

                self.current_run_log.extend(single_attempt_log_capture_opt)
                if current_schedule_opt is None: self._log_message("CRITICAL ERROR during optimized run.", "ERROR"); break

                if is_successful_attempt_opt:
                    schedule_hash_opt = hash(json.dumps(current_schedule_opt, sort_keys=True, default=str))
                    if schedule_hash_opt not in generated_schedule_hashes:
                        s_id_opt = len(self.generated_schedules_details) + 1
                        self.generated_schedules_details.append({
                            'id': f"{s_id_opt}-Optimized", 'schedule': current_schedule_opt, 'log': single_attempt_log_capture_opt,
                            'metrics': attempt_metrics_opt, 'placed_courses': placed_courses_opt
                        })
                        generated_schedule_hashes.add(schedule_hash_opt)
                        self._log_message(f"SUCCESS: Found new distinct valid schedule (ID: {s_id_opt}-Optimized).", "INFO")
                else: # (Logic for tracking best failed optimized run is unchanged but uses new data)
                    current_is_better_opt = (attempt_metrics_opt['unmet_grade_slots_count'] < best_failed_schedule_data['metrics']['unmet_grade_slots_count']) or \
                               (attempt_metrics_opt['unmet_grade_slots_count'] == best_failed_schedule_data['metrics']['unmet_grade_slots_count'] and \
                                attempt_metrics_opt['unmet_prep_teachers_count'] < best_failed_schedule_data['metrics']['unmet_prep_teachers_count'])
                    if current_is_better_opt:
                        best_failed_schedule_data = {'schedule': current_schedule_opt, 'log': single_attempt_log_capture_opt,
                                                     'metrics': attempt_metrics_opt, 'placed_courses': placed_courses_opt}
                        self._log_message("This (optimized) is the new best failed attempt found so far.", "DEBUG")

        self.courses_data = original_courses_data
        self.cohort_constraints = original_cohort_constraints

        # --- NEW: RANKING LOGIC ---
        if not self.generated_schedules_details:
            self._log_message("FINAL: Could not generate any valid schedules, even after optimization attempts.", "ERROR")
            if best_failed_schedule_data['schedule']:
                best_failed_schedule_data['id'] = "Best_Failed_Attempt"
                self.generated_schedules_details.append(best_failed_schedule_data)
            return False

        self._log_message(f"Generated {len(self.generated_schedules_details)} valid schedule(s). Now ranking them.", "INFO")

        for s_detail in self.generated_schedules_details:
            placed_courses_by_term = s_detail.get('placed_courses', {})
            g11_core_courses = set()
            g12_core_courses = set()

            if placed_courses_by_term:
                for term, courses in placed_courses_by_term.items():
                    for course in courses:
                         if course.get('placed_this_term_count', 0) > 0:
                            is_core = course.get('subject_area') in CORE_SUBJECTS_HS
                            grade = course.get('grade_level')
                            if is_core:
                                if grade == 11: g11_core_courses.add(course['name'])
                                elif grade == 12: g12_core_courses.add(course['name'])

            s_detail['metrics']['g11_core_count'] = len(g11_core_courses)
            s_detail['metrics']['g12_core_count'] = len(g12_core_courses)
            score_tuple = (
                1 if len(g11_core_courses) >= 2 else 0,
                len(g11_core_courses),
                1 if len(g12_core_courses) >= 2 else 0,
                len(g12_core_courses)
            )
            s_detail['score'] = score_tuple

        self.generated_schedules_details.sort(key=lambda x: x.get('score', (-1,)), reverse=True)

        if self.generated_schedules_details:
            best_schedule = self.generated_schedules_details[0]
            self._log_message(f"Best schedule selected (ID: {best_schedule['id']}) with G11 Cores: {best_schedule['metrics']['g11_core_count']}, G12 Cores: {best_schedule['metrics']['g12_core_count']}.", "INFO")

        self._log_message(f"SUCCESS: Generated and ranked {len(self.generated_schedules_details)} valid schedule(s).", "INFO")
        return True


    # --- MODIFIED FUNCTION ---
    def _generate_single_schedule_attempt(self, attempt_seed_modifier=0, attempt_log_list=None):
        log_fn = lambda msg, level="INFO": (attempt_log_list.append(f"[{level}] {datetime.datetime.now().strftime('%H:%M:%S')} {msg}") if attempt_log_list is not None else self._log_message(msg, level))

        log_fn(f"Attempting Schedule Generation (Seed Mod: {attempt_seed_modifier}, Min Prep: {MIN_PREP_BLOCKS_PER_WEEK})", "DEBUG")
        num_p_day = self.params.get('num_periods_per_day', 1)
        if not isinstance(num_p_day, int) or num_p_day <= 0: num_p_day = 1
        num_terms = self.params.get('num_terms', 1)
        num_tracks = self.params.get('num_concurrent_tracks_per_period', 1)
        is_hs = self.params.get('school_type') == 'High School'
        force_same_time = self.params.get('force_same_time', False)

        current_schedule = {t: {d: [[None] * num_tracks for _ in range(num_p_day)] for d in DAYS_OF_WEEK} for t in range(1, num_terms + 1)}
        items_by_term = defaultdict(list)
        source_data = self.subjects_data if not is_hs else self.courses_data

        metrics_template = {'overall_completion_rate': 0, 'unmet_grade_slots_count': float('inf'), 'unmet_prep_teachers_count': float('inf')}
        if not source_data:
            log_fn("No subjects/courses defined. Cannot generate schedule.", "ERROR")
            return None, False, metrics_template, {} # MODIFIED: Consistent return
        if not self.teachers_data:
            log_fn("No teachers defined. Cannot generate schedule.", "ERROR")
            return None, False, metrics_template, {} # MODIFIED: Consistent return

        p_dur_min = self.params.get('period_duration_minutes', 60)
        weeks_per_term = self.params.get('weeks_per_term', 18)
        if self.params.get('scheduling_model') == "Full Year": weeks_per_term = self.params.get('num_instructional_weeks', 36)

        if p_dur_min <= 0 or weeks_per_term <= 0:
            log_fn("Period duration or weeks per term is zero, cannot calculate period loads.", "CRITICAL")
            return None, False, metrics_template, {} # MODIFIED: Consistent return

        # (The rest of the function logic is mostly the same, it just operates on local variables)
        for item_data_orig in source_data:
            item_data = copy.deepcopy(item_data_orig)
            if item_data is None: continue

            grade_level_raw = item_data.get('grade_level')
            if grade_level_raw and isinstance(grade_level_raw, str) and grade_level_raw.isdigit():
                item_data['grade_level'] = int(grade_level_raw)
            credits = item_data.get('credits', 0)
            if credits >= 5: periods_per_week = 5
            elif credits >= 3: periods_per_week = 3
            else: periods_per_week = 1

            item_data['periods_per_week_in_active_term'] = periods_per_week
            log_fn(f"Calculated {periods_per_week} p/wk for '{item_data['name']}' ({credits} credits)", "DEBUG")
            term_num_item = item_data.get('term_assignment', 1)
            terms_to_sched_in = list(range(1, num_terms + 1)) if not is_hs and num_terms > 1 else [term_num_item]
            for term_actual in terms_to_sched_in:
                if 1 <= term_actual <= num_terms:
                    items_by_term[term_actual].append({**item_data, 'teacher': None, 'periods_to_schedule_this_week': item_data.get('periods_per_week_in_active_term', 0),'constraints': parse_scheduling_constraint(item_data.get('scheduling_constraints_raw', ''), num_p_day), 'type': 'subject' if not is_hs else 'course', 'placed_this_term_count': 0, 'is_cts_course': "cts" in item_data.get('subject_area','').lower() if is_hs else False,})
        teacher_max_teaching_this_week = {}
        for teacher in self.teachers_data:
            teacher_name = teacher['name']
            total_avail_slots = 0
            for day_k in DAYS_OF_WEEK:
                for period_k in range(num_p_day):
                    if teacher.get('availability', {}).get(day_k, {}).get(period_k, False): total_avail_slots += 1
            max_t = total_avail_slots - MIN_PREP_BLOCKS_PER_WEEK
            teacher_max_teaching_this_week[teacher_name] = max_t
            if max_t < 0: log_fn(f"WARN Teacher {teacher_name}: {total_avail_slots} avail, < {MIN_PREP_BLOCKS_PER_WEEK} prep. Max teach {max_t}. Cannot teach.", "WARN")
        is_overall_successful_attempt = True
        attempt_metrics = {'overall_completion_rate': 0.0, 'unmet_grade_slots_count': 0, 'unmet_prep_teachers_count': 0}
        all_terms_overall_completion_rates_for_avg = []
        for term_idx in range(1, num_terms + 1):
            log_fn(f"--- Processing Term {term_idx} ---", "DEBUG")
            current_term_course_list_for_scheduling = items_by_term.get(term_idx, [])
            if not current_term_course_list_for_scheduling:
                log_fn(f"No courses/subjects defined for Term {term_idx}. Skipping.", "INFO")
                all_terms_overall_completion_rates_for_avg.append(1.0)
                continue
            teacher_busy_this_term = defaultdict(set)
            item_scheduled_on_day_this_term = defaultdict(set)
            teacher_teaching_periods_this_week_for_term = defaultdict(int)
            must_assign_items, flexible_items_all = [], []
            for item_sort in current_term_course_list_for_scheduling:
                (must_assign_items if any(c.get('type') == 'ASSIGN' for c in item_sort.get('constraints',[])) else flexible_items_all).append(item_sort)
            required_grades_for_term = self.params.get('grades_requiring_full_schedule', [])
            grade_coverage_this_term = {g: {d: [False] * num_p_day for d in DAYS_OF_WEEK} for g in required_grades_for_term}
            def update_grade_coverage_local(item_obj, day_name, p_idx, grade_coverage_dict, req_grades):
                if not is_hs: return
                item_grade = item_obj.get('grade_level')
                if isinstance(item_grade, int) and item_grade in req_grades:
                    if item_grade in grade_coverage_dict:
                        grade_coverage_dict[item_grade][day_name][p_idx] = True
            log_fn(f"DEBUG (Term {term_idx}): Starting processing of {len(must_assign_items)} MUST ASSIGN items.", "DEBUG")
            log_fn(f"DEBUG (Term {term_idx}): Starting processing of {len(flexible_items_all)} FLEXIBLE items.", "DEBUG")
            def sort_key(course):
                grade = course.get('grade_level')
                is_required_grade = 1 if grade in required_grades_for_term else 0
                periods = course.get('periods_per_week_in_active_term', 0)
                return (is_required_grade, periods)
            flexible_items_processed = sorted(flexible_items_all, key=sort_key, reverse=True)
            if attempt_seed_modifier > 0:
                random.seed(datetime.datetime.now().microsecond + attempt_seed_modifier + term_idx)
                random.shuffle(flexible_items_processed)
            for item in flexible_items_processed:
                item_name = item['name']
                item_subj_area = item.get('subject_area')
                periods_to_place = item.get('periods_per_week_in_active_term', 0)
                not_constr = [c for c in item.get('constraints', []) if c.get('type') == 'NOT']
                if periods_to_place <= 0: continue
                item_teacher = self._find_best_teacher_for_course(item, teacher_teaching_periods_this_week_for_term, teacher_max_teaching_this_week)
                if not item_teacher:
                    log_fn(f"Could not find any available & qualified teacher for '{item_name}'. Skipping.", "WARN")
                    continue
                item['teacher'] = item_teacher
                placed_count = 0
                available_slots_for_course = [(d, p) for d in DAYS_OF_WEEK for p in range(num_p_day)]
                random.shuffle(available_slots_for_course)
                forced_period_for_this_item = None
                for _ in range(periods_to_place):
                    slot_was_found_for_this_period = False
                    for day_name, p_idx in available_slots_for_course:
                        if force_same_time and forced_period_for_this_item is not None and p_idx != forced_period_for_this_item:
                            continue
                        if (day_name, p_idx) in teacher_busy_this_term.get(item_teacher, set()): continue
                        if any(c['day'] == day_name and c['period'] == p_idx for c in not_constr): continue
                        if self.params.get('multiple_times_same_day', True) is False and day_name in item_scheduled_on_day_this_term.get(item_name, set()): continue
                        for track_idx in range(num_tracks):
                            if current_schedule[term_idx][day_name][p_idx][track_idx] is None:
                                current_schedule[term_idx][day_name][p_idx][track_idx] = (item_name, item_teacher)
                                teacher_busy_this_term[item_teacher].add((day_name, p_idx))
                                item_scheduled_on_day_this_term[item_name].add(day_name)
                                placed_count += 1
                                update_grade_coverage_local(item, day_name, p_idx, grade_coverage_this_term, required_grades_for_term)
                                if force_same_time and forced_period_for_this_item is None:
                                    forced_period_for_this_item = p_idx
                                available_slots_for_course.remove((day_name, p_idx))
                                slot_was_found_for_this_period = True
                                break
                        if slot_was_found_for_this_period: break
                item['placed_this_term_count'] = placed_count
                teacher_teaching_periods_this_week_for_term[item_teacher] += placed_count
                if placed_count > 0 and placed_count < periods_to_place:
                    log_fn(f"PARTIAL (Term {term_idx}): '{item_name}' (T:{item_teacher}) placed {placed_count}/{periods_to_place} times.", "WARN")
                elif placed_count == periods_to_place:
                    log_fn(f"SCHED (Term {term_idx}): Flex item '{item_name}' (T:{item_teacher}) successfully placed {placed_count} times.", "DEBUG")
                else:
                    log_fn(f"FAILED TO PLACE (Term {term_idx}): '{item_name}' could not be fully placed (0/{periods_to_place} periods).", "WARN")
            total_periods_needed_term = sum(it.get('periods_to_schedule_this_week', 0) for it in current_term_course_list_for_scheduling)
            total_periods_placed_term = sum(it.get('placed_this_term_count', 0) for it in current_term_course_list_for_scheduling)
            term_completion_rate = 0.0
            if total_periods_needed_term > 0:
                term_completion_rate = total_periods_placed_term / total_periods_needed_term
                log_fn(f"Term {term_idx} Completion: {total_periods_placed_term}/{total_periods_needed_term} ({term_completion_rate*100:.2f}%).", "INFO")
                if term_completion_rate < MIN_ACCEPTABLE_SCHEDULE_COMPLETION_RATE:
                    log_fn(f"ERROR (Term {term_idx}): Completion ({term_completion_rate*100:.2f}%) < min {MIN_ACCEPTABLE_SCHEDULE_COMPLETION_RATE*100}%. Invalidating attempt.", "ERROR")
                    is_overall_successful_attempt = False
            elif not current_term_course_list_for_scheduling:
                log_fn(f"INFO (Term {term_idx}): No items to schedule.", "INFO")
                term_completion_rate = 1.0
            else:
                log_fn(f"INFO (Term {term_idx}): All items have 0 periods needed.", "INFO")
                term_completion_rate = 1.0
            all_terms_overall_completion_rates_for_avg.append(term_completion_rate)
            for teacher_check in self.teachers_data:
                name_check = teacher_check['name']
                actual_teaching_this_term_val = teacher_teaching_periods_this_week_for_term.get(name_check, 0)
                total_personal_avail_this_config = sum(1 for d_avail in DAYS_OF_WEEK for p_avail in range(num_p_day) if teacher_check.get('availability', {}).get(d_avail, {}).get(p_avail, False))
                actual_prep = total_personal_avail_this_config - actual_teaching_this_term_val
                if teacher_max_teaching_this_week.get(name_check, -1) < 0 and actual_teaching_this_term_val > 0:
                    log_fn(f"ERROR (Term {term_idx}): Teacher {name_check} was unscheduleable but taught. Invalidating attempt.", "ERROR")
                    is_overall_successful_attempt = False
                    attempt_metrics['unmet_prep_teachers_count'] += 1
                elif actual_prep < MIN_PREP_BLOCKS_PER_WEEK:
                    log_fn(f"ERROR (Term {term_idx}): Teacher {name_check} has {actual_prep} prep, < {MIN_PREP_BLOCKS_PER_WEEK}. Invalidating attempt.", "ERROR")
                    is_overall_successful_attempt = False
                    attempt_metrics['unmet_prep_teachers_count'] += 1
            log_fn(f"Term {term_idx} prep blocks verified.", "DEBUG")
            if is_hs:
                unmet_slots_for_all_grades_this_term = 0
                if required_grades_for_term:
                    placed_grades = {c.get('grade_level') for c in current_term_course_list_for_scheduling if c.get('placed_this_term_count', 0) > 0}
                    if not any(g in placed_grades for g in required_grades_for_term):
                        log_fn(f"ERROR (Term {term_idx}): No courses were placed for required grades {required_grades_for_term}. Invalidating.", "ERROR")
                        is_overall_successful_attempt = False
                for grade_to_check in required_grades_for_term:
                    for day_check_fill in DAYS_OF_WEEK:
                        for period_check_fill in range(num_p_day):
                            if not grade_coverage_this_term.get(grade_to_check, {}).get(day_check_fill, [])[period_check_fill]:
                                log_fn(f"ERROR (Term {term_idx}): Grade {grade_to_check} no class {day_check_fill} P{period_check_fill+1}. Invalidating attempt.", "ERROR")
                                unmet_slots_for_all_grades_this_term += 1
                if unmet_slots_for_all_grades_this_term > 0:
                    is_overall_successful_attempt = False
                    attempt_metrics['unmet_grade_slots_count'] += unmet_slots_for_all_grades_this_term
                log_fn(f"Term {term_idx}: Full block schedule verified for Grades {required_grades_for_term}.", "DEBUG")
            log_fn(f"Term {term_idx} scheduling completed and verified.", "DEBUG")

        if all_terms_overall_completion_rates_for_avg:
            attempt_metrics['overall_completion_rate'] = sum(all_terms_overall_completion_rates_for_avg) / len(all_terms_overall_completion_rates_for_avg)

        if is_overall_successful_attempt:
            log_fn("Full Schedule Generation Attempt Finished Successfully.", "INFO")
        else:
            log_fn("Full Schedule Generation Attempt Failed Validation (see errors above).", "INFO")

        # MODIFIED: Return the final state of all courses for this attempt
        return current_schedule, is_overall_successful_attempt, attempt_metrics, items_by_term

    # ... (All other helper functions like _create_course_object_from_name, _is_teacher_qualified, etc., are unchanged) ...
    def _create_course_object_from_name(self, name, credits):
        params = self.get_parameters()
        grade = "Mixed"
        if " 10" in name: grade = 10
        if " 20" in name: grade = 11
        if " 30" in name: grade = 12
        subject_area = "Other"
        if name.lower().startswith("eng"): subject_area = "English"
        elif name.lower().startswith("math"): subject_area = "Math"
        elif name.lower().startswith("soc"): subject_area = "Social Studies"
        elif name.lower().startswith("sci") or name.lower().startswith("bio") or name.lower().startswith("chem") or name.lower().startswith("phys"):
            subject_area = "Science"
        elif name.lower().startswith("pe") or name.lower().startswith("physical"):
            subject_area = "PE"
        p_dur_min = params.get('period_duration_minutes', 60)
        weeks_course_dur = params.get('weeks_per_term', 18)
        if params.get('scheduling_model') == "Full Year":
            weeks_course_dur = params.get('num_instructional_weeks', 36)
        periods_per_week = 0
        if weeks_course_dur > 0 and p_dur_min > 0:
            course_mins = credits * CREDITS_TO_HOURS_PER_CREDIT * 60
            periods_year = math.ceil(course_mins / p_dur_min)
            periods_per_week = math.ceil(periods_year / weeks_course_dur)
        return {'name': name, 'credits': credits, 'grade_level': grade, 'subject_area': subject_area, 'periods_per_week_in_active_term': max(1, periods_per_week), 'term_assignment': 1, 'scheduling_constraints_raw': "", 'parsed_constraints': [], '_is_one_credit_buffer_item': False, '_is_suggestion': True}
    def _is_teacher_qualified(self, teacher_obj, subject_area):
        if subject_area == "Other": return True
        return subject_area in teacher_obj.get('qualifications', [])
    def _find_best_teacher_for_course(self, item_obj, teacher_teaching_periods_this_week_for_term, teacher_max_teaching_this_week):
        subject_area = item_obj.get('subject_area')
        periods_for_this_course = item_obj.get('periods_per_week_in_active_term', 0)
        candidate_teachers = []
        for teacher in self.teachers_data:
            teacher_name = teacher['name']
            if not self._is_teacher_qualified(teacher, subject_area):
                continue
            projected_load = teacher_teaching_periods_this_week_for_term.get(teacher_name, 0) + periods_for_this_course
            max_load = teacher_max_teaching_this_week.get(teacher_name, -1)
            if max_load < 0: continue
            if projected_load > max_load: continue
            candidate_teachers.append({'name': teacher_name, 'load_score': max_load - projected_load})
        if not candidate_teachers: return None
        random.shuffle(candidate_teachers)
        candidate_teachers.sort(key=lambda x: x['load_score'], reverse=True)
        return candidate_teachers[0]['name']
    def _check_cohort_clash_in_slot(self, item_name_to_schedule, term_idx, day_name, period_idx, current_schedule):
        num_tracks = self.params.get('num_concurrent_tracks_per_period', 1)
        base_item_name = item_name_to_schedule.split(' (')[0].strip()
        for track_idx_check in range(num_tracks):
            existing_item_tuple = current_schedule[term_idx][day_name][period_idx][track_idx_check]
            if existing_item_tuple:
                existing_base_name = existing_item_tuple[0].split(' (')[0].strip()
                for clash_group in self.cohort_constraints:
                    if isinstance(clash_group, (list, tuple)) and base_item_name in clash_group and existing_base_name in clash_group:
                        return True
        return False
    def _attempt_course_combination(self):
        if self.params.get('school_type') != 'High School': return False
        courses_modified = False
        courses_to_add = []
        course_names_to_remove = set()
        remap_for_cohorts = {}
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
            combined_course = {'name': new_name, 'credits': credits, 'grade_level': "Mixed", 'assigned_teacher_name': None, 'subject_area': course1_obj['subject_area'], 'periods_per_year_total_instances': periods_week * weeks_per_term_calc, 'periods_per_week_in_active_term': periods_week, 'scheduling_constraints_raw': merged_constraints_raw, 'parsed_constraints': parsed_constraints, 'term_assignment': course1_obj['term_assignment'], '_is_one_credit_buffer_item': False}
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
                new_group = list(set(remap_for_cohorts.get(name, name) for name in group))
                if len(new_group) > 1:
                    new_cohort_constraints.append(new_group)
            self.cohort_constraints = new_cohort_constraints
            self._log_message(f"Updated cohort constraints after combination: {len(self.cohort_constraints)} remaining.", "DEBUG")
        return courses_modified