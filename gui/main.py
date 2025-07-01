# scheduler_ui_controller.py (Corrected File)

import sys
import os
import datetime
import math
import random
import copy
import json
import traceback
from collections import defaultdict

from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

try:
    from tabulate import tabulate
except ImportError:
    tabulate = None

# --- Import from the engine ---
from scheduler_engine import (
    SchedulingEngine, QUALIFIABLE_SUBJECTS, HIGH_SCHOOL_COURSE_CREDITS_TEMPLATE,
    GRADES_REQUIRING_FULL_SCHEDULE, MIN_PREP_BLOCKS_PER_WEEK,
    MIN_ACCEPTABLE_SCHEDULE_COMPLETION_RATE, ELEMENTARY_MIN_HOURS, HIGH_SCHOOL_MIN_HOURS,
    MAX_DISTINCT_SCHEDULES_TO_GENERATE, MAX_SCHEDULE_GENERATION_ATTEMPTS, CREDITS_TO_HOURS_PER_CREDIT, CTS_KEYWORDS,
    TYPICAL_COURSE_CREDITS_FOR_ESTIMATE, CORE_COURSE_BASE_NAMES, PERIODS_PER_TYPICAL_OPTION_BLOCK,
    DAYS_OF_WEEK,
    parse_date, parse_time, calculate_instructional_days,
    parse_teacher_availability, parse_scheduling_constraint,
    format_time_from_minutes, time_to_minutes
)

class ConsoleUIController:
    """
    Controls the user interface (console-based) for the scheduler.
    It interacts with the user, collects data, passes it to the engine,
    retrieves results, and displays them.
    """
    def __init__(self):
        self.engine = SchedulingEngine()
        self.session_cache = {}

    def run(self):
        """Main application loop."""
        print("Welcome to the School Scheduler!")
        self._load_session_cache()

        while True:
            current_run_cache_backup = copy.deepcopy(self.session_cache)
            try:
                self._run_once()
                self._save_session_cache()
            except KeyboardInterrupt:
                print("\n--- Script interrupted. Exiting. ---")
                break
            except Exception as e_run:
                print(f"\n!!! UNEXPECTED ERROR IN UI CONTROLLER !!!\nType: {type(e_run).__name__}\nMessage: {e_run}")
                traceback.print_exc()
                print("Attempting to restore cache to state before this run.")
                self.session_cache = current_run_cache_backup
            
            if self.get_input_with_default("run_again", "\nMake changes and try again?", str, choices=['yes', 'no']).lower() != 'yes':
                print("INFO: Session cache 'scheduler_session_cache.tmp' retained.")
                break
            print("\n" + "="*25 + " RESTARTING WITH MODIFICATIONS " + "="*25 + "\n")
        
        print("\n--- Script Finished ---")
        
    def _run_once(self):
        """Executes a single, complete scheduling run from input to output."""
        self.display_info_needed()
        
        params = self.engine.get_parameters()
        self.get_school_type(params)
        self.get_operational_parameters(params)
        self.get_course_structure_model(params)
        self.get_period_structure_details(params)
        self.engine.set_parameters(params)

        teachers = self._get_list_data('teachers_data', 'teacher', 'teachers', self._get_teacher_details)
        if not teachers:
            print("CRITICAL: No teachers defined. Cannot schedule.")
            return
        self.engine.set_teachers(teachers)

        school_type = self.engine.get_parameters().get('school_type')
        if school_type == 'Elementary':
            subjects = self._get_list_data('subjects_data', 'subject', 'subjects', self._get_elementary_subject_details)
            if not subjects: print("WARNING: No subjects defined for elementary school."); return
            self.engine.set_subjects(subjects)
        elif school_type == 'High School':
            courses = self.get_high_school_courses()
            if not courses: print("WARNING: No courses defined for high school."); return
            self.engine.set_courses(courses) # Set courses now so constraints can see them
            constraints = self._get_list_data('cohort_constraints_list', 'cohort constraint group', 'cohort constraints', self._get_single_cohort_constraint_details)
            self.engine.set_cohort_constraints(constraints)

        num_schedules_to_generate = self.get_input_with_default('num_schedules_to_generate', 
            f"How many distinct valid schedules to attempt (1-{MAX_DISTINCT_SCHEDULES_TO_GENERATE})?", 
            int, lambda x: 1 <= x <= MAX_DISTINCT_SCHEDULES_TO_GENERATE, default_value_override=1)
        
        max_attempts = num_schedules_to_generate * (MAX_SCHEDULE_GENERATION_ATTEMPTS // MAX_DISTINCT_SCHEDULES_TO_GENERATE)

        print(f"\n--- Telling Engine to Generate Schedules (Max Attempts: {max_attempts}) ---")
        success = self.engine.generate_schedules(num_schedules_to_generate, max_attempts)

        generated_schedules = self.engine.get_generated_schedules()
        if success:
            print(f"\nSUCCESS: Engine generated {len(generated_schedules)} valid schedule(s).")
        else:
            print("\nWARNING: Engine could not generate any valid schedules.")
            if generated_schedules:
                 print("\n--- Displaying Best Failed Schedule Attempt ---")

        if generated_schedules:
            self.display_schedules_console()
            if self.get_input_with_default("export_pdf", "\nExport to PDF?", str, choices=['yes', 'no']).lower() == 'yes':
                self.export_schedules_pdf()

        if self.get_input_with_default("view_log", "\nView detailed operational log from the engine?", str, choices=['yes', 'no']).lower() == 'yes':
            print("\n--- Engine Operational Log ---")
            for msg in self.engine.get_run_log():
                print(msg)
            print("--- End Log ---")
            
    # --- FIX: THIS FUNCTION HAS BEEN CORRECTED ---
    # It now properly caches the text of a choice (e.g., "Yes") instead of its index ("1"),
    # making the cache more readable and robust between runs.
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
                    # Try to find the index of the cached value to display the text
                    idx = -1
                    if isinstance(cached_value, str) and cached_value.isdigit():
                        idx = int(cached_value) - 1 # Handles old-style numeric cache
                    elif isinstance(cached_value, int):
                        idx = cached_value - 1
                    elif isinstance(cached_value, str) and cached_value in choices:
                        idx = choices.index(cached_value)
                    
                    if 0 <= idx < len(choices):
                        default_display = choices[idx]
                except (ValueError, TypeError, IndexError):
                     # If index lookup fails, just use the cached string if it's a valid choice
                    if isinstance(cached_value, str) and cached_value in choices:
                        default_display = cached_value
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
                            value_to_cache = choices[choice_idx] # Store text, not number
                        else: print(f"Invalid choice number."); continue
                    except ValueError:
                        matched_choice = next((c for c in choices if c.lower() == value_to_process.lower()), None)
                        if matched_choice:
                            converted_value = matched_choice
                            value_to_cache = matched_choice
                        else:
                            print(f"Invalid choice text."); continue
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
    # --- END OF FIX ---

    def display_info_needed(self):
        print("\n--- Information Needed to Complete the Schedule ---")
        print("\n**General School Information:**")
        print("  - School Name, Year Start/End Dates, Non-Instructional Days")
        print("  - Daily School Start Time")
        print("  - Policy: Can classes appear multiple times on the same day?")
        print("\n**Schedule Structure:**")
        print("  - Type: Quarterly, Semester, or Full Year")
        print("  - Number of teaching periods/day, Duration of periods, Duration of breaks")
        print("  - Duration of lunch and after which period it occurs")
        print("  - Number of concurrent class slots (tracks) per period")
        # Use the property from the engine's parameters for dynamic display
        grades_display = self.engine.get_parameters().get('grades_requiring_full_schedule', GRADES_REQUIRING_FULL_SCHEDULE)
        print(f"  - (Scheduler will ensure Grades {', '.join(map(str, grades_display))} have a class offering in every period slot)")
        print("\n**Teacher Information:**")
        print(f"  - Teacher Names, Availability/Unavailability (e.g., 'Unavailable Mon P1-P2')")
        print(f"  - Subjects each teacher is qualified to teach (from list: {', '.join(QUALIFIABLE_SUBJECTS)})")
        print(f"  - (The system will aim for at least {MIN_PREP_BLOCKS_PER_WEEK} prep blocks per teacher per week within their availability)")
        print("\n**Course/Subject Information:**")
        print(f"  - (The system will aim to schedule at least {MIN_ACCEPTABLE_SCHEDULE_COMPLETION_RATE*100:.0f}% of requested course periods per term)")
        print("  - **(Optimizer)** If scheduling fails, it can auto-combine low-stream courses (e.g., Sci 14 + Sci 10-4) to improve success.")
        print("  **Elementary:** Subjects, Periods/week, Constraints (e.g., 'Math NOT P1')")
        print("  **High School:** Courses, Credits, Grade Level (10, 11, 12, or Mixed), Subject Area, Term, Constraints, Cohort Clashes")
        input("\nPress Enter to continue...")
        print("-" * 50)

    def get_school_type(self, params_dict):
        print("\n--- School Type Selection ---")
        school_type_choice = self.get_input_with_default('school_type_choice', "School Type", str, choices=['Elementary', 'High School'])
        if school_type_choice == "Elementary":
            params_dict['school_type'], params_dict['min_instructional_hours'] = "Elementary", ELEMENTARY_MIN_HOURS
        elif school_type_choice == "High School":
            params_dict['school_type'], params_dict['min_instructional_hours'] = "High School", HIGH_SCHOOL_MIN_HOURS
        self.session_cache['min_instructional_hours'] = params_dict.get('min_instructional_hours')

    def get_operational_parameters(self, params_dict):
        print("\n--- School Operational Parameters ---")
        params_dict['school_name'] = self.get_input_with_default('school_name', "School Name", str, lambda x: len(x) > 0)
        while True:
            start_date_str = self.get_input_with_default('start_date_str', "School Year Start Date (YYYY-MM-DD)", str)
            params_dict['start_date'] = parse_date(start_date_str)
            if params_dict['start_date']:
                self.session_cache['start_date_str'] = start_date_str
                break
            else: print("Invalid date format.")
        while True:
            end_date_str = self.get_input_with_default('end_date_str', "School Year End Date (YYYY-MM-DD)", str)
            params_dict['end_date'] = parse_date(end_date_str)
            if params_dict['end_date'] and params_dict.get('start_date') and params_dict['end_date'] > params_dict['start_date']:
                self.session_cache['end_date_str'] = end_date_str
                break
            else: print("Invalid date format or end date not after start date.")

        autofill_choice = self.get_input_with_default('autofill_holidays', "Autofill non-instructional days (stats, breaks, PD)?", str, choices=['Yes', 'No'], default_value_override='No')

        default_days_str = self.session_cache.get('non_instructional_days_str')
        if autofill_choice.lower() == 'yes':
            print("Requesting suggested non-instructional days from engine...")
            self.engine.set_parameters(params_dict) 
            suggested_days = self.engine.suggest_non_instructional_days()
            if suggested_days:
                print("Done. The suggestion will be used as the default.")
                default_days_str = suggested_days
            else: print("WARN: Engine could not generate suggestion. Please enter manually.")

        params_dict['non_instructional_days_str'] = self.get_input_with_default( 'non_instructional_days_str', "Non-instructional days (YYYY-MM-DD, comma-separated)", str, allow_empty=True, default_value_override=default_days_str)
        
        while True:
            start_time_str = self.get_input_with_default('start_time_str', "Daily School Start Time (HH:MM AM/PM or HH:MM)", str)
            params_dict['school_start_time'] = parse_time(start_time_str)
            if params_dict['school_start_time']:
                self.session_cache['start_time_str'] = start_time_str
                break
            else: print("Invalid time format.")

        multiple_choice = self.get_input_with_default('multiple_times_same_day_choice', "Can a specific course/subject appear multiple times on the same day's schedule?", str, choices=['yes', 'no'])
        params_dict['multiple_times_same_day'] = multiple_choice.lower() == 'yes'
        params_dict['instructional_days'] = calculate_instructional_days(params_dict.get('start_date'), params_dict.get('end_date'), params_dict.get('non_instructional_days_str',''))
        self.session_cache['instructional_days'] = params_dict.get('instructional_days')
        num_id = params_dict.get('instructional_days',0)
        params_dict['num_instructional_weeks'] = math.ceil(num_id / 5) if num_id > 0 else 0
        self.session_cache['num_instructional_weeks'] = params_dict.get('num_instructional_weeks')
        print(f"INFO: Calculated Instructional Days: {params_dict.get('instructional_days')}, Weeks: {params_dict.get('num_instructional_weeks')}")

    def get_course_structure_model(self, params_dict):
        print("\n--- Course Structure Model ---")
        model_choices_map = {"Quarterly": ("Quarterly", 4), "Semester": ("Semester", 2), "Full Year": ("Full Year", 1)}
        chosen_model_text = self.get_input_with_default('course_model_choice_text', "Select scheduling model", str, choices=list(model_choices_map.keys()))
        params_dict['scheduling_model'], params_dict['num_terms'] = model_choices_map[chosen_model_text]
        num_iw, num_t = params_dict.get('num_instructional_weeks',0), params_dict.get('num_terms',0)
        params_dict['weeks_per_term'] = math.ceil(num_iw / num_t) if num_iw > 0 and num_t > 0 else 0
        self.session_cache['weeks_per_term'] = params_dict.get('weeks_per_term')

    def get_period_structure_details(self, params_dict):
        print("\n--- Daily Period Structure & Timing ---")
        params_dict['num_concurrent_tracks_per_period'] = self.get_input_with_default('num_concurrent_tracks_per_period', "Number of concurrent class slots (tracks) per period", int, lambda x: x >= 1)

        while True:
            print("\n--- Define Daily Period and Break Timings ---")
            num_p = self.get_input_with_default('num_periods_per_day', "Number of teaching periods/day", int, lambda x: x > 0)
            p_dur = self.get_input_with_default('period_duration_minutes', "Duration of each period (minutes)", int, lambda x: x > 0)
            b_dur_str = self.get_input_with_default('break_between_classes_minutes_str', "Duration of breaks between classes (minutes)", str, allow_empty=True, default_value_override='5')
            b_dur = int(b_dur_str) if b_dur_str.isdigit() and int(b_dur_str) >= 0 else 5
            lunch_dur = self.get_input_with_default('lunch_duration_minutes', "Duration of lunch break (minutes)", int, lambda x: x >= 0)
            lunch_after_p = 0
            if lunch_dur > 0:
                lunch_after_p = self.get_input_with_default('lunch_after_period_num', f"Lunch occurs AFTER which period? (1-{num_p})", int, lambda x: 1 <= x <= num_p)

            s_start_t = params_dict.get('school_start_time')
            if not s_start_t:
                raise Exception("Cannot proceed without a school start time.")

            current_m, period_times_minutes, lunch_start_m, lunch_end_m = time_to_minutes(s_start_t), [], None, None
            for i in range(num_p):
                period_start_m, period_end_m = current_m, current_m + p_dur
                period_times_minutes.append((period_start_m, period_end_m))
                current_m = period_end_m
                if lunch_dur > 0 and (i + 1) == lunch_after_p:
                    lunch_start_m = current_m
                    current_m += lunch_dur
                    lunch_end_m = current_m
                elif i < num_p - 1:
                    current_m += b_dur
            school_end_m = current_m
            
            print("\n--- Calculated Daily Schedule ---")
            print(f"  School Start: {format_time_from_minutes(time_to_minutes(s_start_t))}")
            for i, (p_start, p_end) in enumerate(period_times_minutes):
                print(f"  Period {i+1}:      {format_time_from_minutes(p_start)} - {format_time_from_minutes(p_end)} ({p_dur} min)")
                if lunch_dur > 0 and (i + 1) == lunch_after_p:
                    print(f"  ** LUNCH **:    {format_time_from_minutes(p_end)} - {format_time_from_minutes(p_end + lunch_dur)} ({lunch_dur} min)")
                elif i < num_p - 1:
                    print(f"  Break:          {format_time_from_minutes(p_end)} - {format_time_from_minutes(p_end + b_dur)} ({b_dur} min)")
            print(f"  School End:   {format_time_from_minutes(school_end_m)}")
            
            if self.get_input_with_default(None, "Is this schedule correct?", str, choices=['Yes', 'No']).lower() == 'yes':
                params_dict['num_periods_per_day'] = num_p
                params_dict['period_duration_minutes'] = p_dur
                params_dict['break_between_classes_minutes'] = b_dur
                def minutes_to_time_obj(mins):
                    if mins is None: return None
                    h, m = divmod(mins, 60)
                    return datetime.time(hour=int(h) % 24, minute=int(m))
                params_dict['school_end_time'] = minutes_to_time_obj(school_end_m)
                params_dict['lunch_start_time'] = minutes_to_time_obj(lunch_start_m)
                params_dict['lunch_end_time'] = minutes_to_time_obj(lunch_end_m)
                params_dict['period_times_minutes'] = period_times_minutes
                self.session_cache.update({
                    'lunch_duration_minutes': lunch_dur, 'lunch_after_period_num': lunch_after_p,
                    'break_between_classes_minutes_str': str(b_dur)
                })
                break
        
        print("\n--- Advanced Scheduling Preferences ---")
        force_same_time_choice = self.get_input_with_default('force_same_time_slot_choice', "Try to force multi-period classes to the same time each day?", str, choices=['Yes', 'No'], default_value_override='No')
        if force_same_time_choice.lower() == 'yes': print("  -> WARNING: This strong constraint can make scheduling difficult or impossible.")
        params_dict['force_same_time_slot'] = (force_same_time_choice.lower() == 'yes')
        
        total_annual_hours = (params_dict.get('instructional_days', 0) * params_dict.get('num_periods_per_day', 0) * params_dict.get('period_duration_minutes', 0)) / 60
        params_dict['total_annual_instructional_hours'] = total_annual_hours
        if total_annual_hours < params_dict.get('min_instructional_hours',0):
            print(f"WARNING: Calculated annual hours ({total_annual_hours:.2f}) are below the required minimum of {params_dict.get('min_instructional_hours',0)}.")

    def _get_list_data(self, data_key, item_name_singular, item_name_plural, get_item_details_func):
        print(f"\n--- {item_name_plural.capitalize()} Information ---")
        current_items = copy.deepcopy(self.session_cache.get(data_key, []))
        
        # --- FIX: ADD THIS BLOCK ---
        # Re-parse teacher availability based on the CURRENT number of periods per day.
        # This prevents using stale availability maps from the cache.
        if data_key == 'teachers_data':
            num_p_day_current = self.engine.get_parameters().get('num_periods_per_day', 1)
            # Ensure it's a valid integer
            if not isinstance(num_p_day_current, int) or num_p_day_current <= 0:
                num_p_day_current = 1
            for teacher in current_items:
                raw_availability = teacher.get('raw_availability_str', "")
                teacher['availability'] = parse_teacher_availability(raw_availability, num_p_day_current)
        # --- END OF FIX ---

        if data_key == 'courses_data_raw_input' and self.engine.get_parameters().get('school_type') == 'High School' and not current_items:
            self._handle_initial_course_suggestions(current_items)

        while True:
            print(f"\n--- Current {item_name_plural} ({len(current_items)}) ---")
            if not current_items: print(f"No {item_name_plural} defined yet.")
            else:
                for idx, item in enumerate(current_items): self._display_list_item(idx, item, data_key)

            action = self._get_list_action(data_key, current_items)
            
            if action.startswith("Finish"): break
            elif action in ["Add new", "Add custom course/block"]:
                new_item_data = get_item_details_func(defaults=None)
                if new_item_data: current_items.append(new_item_data)
            elif action == "Add from template":
                new_courses = self._add_courses_from_template(current_items)
                if new_courses: current_items.extend(new_courses)
            elif action == "Edit existing" and current_items:
                self._edit_list_item(current_items, item_name_singular, get_item_details_func)
            elif action == "Delete existing" and current_items:
                self._delete_list_item(current_items, item_name_singular)
            elif action == "Clear all":
                current_items = []
                print(f"All {item_name_plural} cleared.")
            elif action == "Suggest more":
                new_suggestions = self.engine.suggest_new_courses_from_capacity(current_items)
                if new_suggestions:
                    print("\n--- Engine Suggested New CTS Courses (based on capacity) ---")
                    for s in new_suggestions: print(f"  - {s['name']} (P/Wk: {s.get('periods_per_week_in_active_term')})")
                    if self.get_input_with_default(None, "Add these to your list?", str, choices=['yes','no']).lower() == 'yes':
                        current_items.extend(new_suggestions)
                else: print("\nEngine found no further capacity for new courses.")


        self.session_cache[data_key] = current_items
        print(f"\nFinalized {item_name_plural} list with {len(current_items)} entries.")
        return current_items

    def _handle_initial_course_suggestions(self, current_items):
        if not self.engine.teachers_data:
            print("\nWARNING: Cannot suggest courses without defined teachers. Proceeding to manual entry.")
            return

        print("\nRequesting course suggestions from the engine...")
        initial_suggestions = self.engine.suggest_core_courses()
        
        if not initial_suggestions:
            print("Engine could not generate suggestions (check teacher availability). Proceeding to manual entry.")
            return

        print("\n--- Suggested Courses & CTS Options (auto-filled based on capacity) ---")
        for idx, s in enumerate(initial_suggestions):
            print(f"  {idx+1}. {s['name']} (Gr: {s['grade_level']}, Term: {s['term_assignment']}, P/Wk: {s.get('periods_per_week_in_active_term')})")
        
        choice = self.get_input_with_default(None, "How to proceed with suggestions?", str, choices=["Use all", "Use grouped blocks instead", "Let me prune the list", "Ignore and enter manually"])

        if choice == "Use all":
            current_items.extend(initial_suggestions)
        elif choice == "Use grouped blocks instead":
            grouped = self.engine.suggest_grouped_courses()
            if grouped: current_items.extend(grouped)
            else: print("Could not generate grouped suggestions.")
        elif choice == "Let me prune the list":
            pruned_list = copy.deepcopy(initial_suggestions)
            while True:
                print("\n--- Pruning Suggested List ---")
                for idx, item in enumerate(pruned_list): print(f"  {idx+1}. {item['name']}")
                del_input = input("Enter number to delete (or 'done'): ").strip()
                if del_input.lower() == 'done': break
                try:
                    del_idx = int(del_input) - 1
                    if 0 <= del_idx < len(pruned_list): pruned_list.pop(del_idx)
                    else: print("Invalid number.")
                except ValueError: print("Invalid input.")
            current_items.extend(pruned_list)

    def _display_list_item(self, idx, item, data_key):
        name_attr = item.get('name', f"Item {idx+1}"); details_str = ""
        if data_key == 'teachers_data':
            avail_str = item.get('raw_availability_str') or "Always Available"
            details_str = f"(Quals: {', '.join(item.get('qualifications',[]))}; Avail: {avail_str})"
        elif data_key == 'courses_data_raw_input':
            details_str = f"(Crs: {item.get('credits')}, Gr: {item.get('grade_level')}, T: {item.get('term_assignment')}, P/Wk: {item.get('periods_per_week_in_active_term')})"
        elif data_key == 'cohort_constraints_list':
            details_str = f"Clash between: {', '.join(item)}"
            name_attr = f"Constraint {idx+1}"
        print(f"  {idx+1}. {name_attr} {details_str}")

    def _get_list_action(self, data_key, current_items):
        is_hs_courses = (data_key == 'courses_data_raw_input' and self.engine.get_parameters().get('school_type') == 'High School')
        choices = ["Add new", "Edit existing", "Delete existing", "Clear all", "Finish"]
        if not current_items:
            choices = ["Add new", "Finish (empty list)"]
        
        if is_hs_courses:
            choices.insert(1, "Add from template")
            if current_items: choices.insert(2, "Suggest more")

        # Adjust for cohort constraints which don't have a template
        if data_key == 'cohort_constraints_list':
            choices = [c for c in choices if c not in ["Add from template", "Suggest more"]]
        
        return self.get_input_with_default(f'{data_key}_action', "Action", str, choices=choices)

    def _edit_list_item(self, current_items, item_name_singular, get_item_details_func):
        try:
            edit_idx_str = self.get_input_with_default(None, f"Enter number of the {item_name_singular} to edit", str)
            edit_idx = int(edit_idx_str) - 1
            if 0 <= edit_idx < len(current_items):
                print(f"\n--- Editing {item_name_singular}: '{current_items[edit_idx].get('name', f'Item {edit_idx+1}')}' ---")
                updated_item = get_item_details_func(defaults=copy.deepcopy(current_items[edit_idx]))
                if updated_item:
                    current_items[edit_idx] = updated_item
            else: print("Invalid number.")
        except (ValueError, TypeError): print("Invalid input.")

    def _delete_list_item(self, current_items, item_name_singular):
        try:
            del_idx_str = self.get_input_with_default(None, f"Enter number of the {item_name_singular} to delete", str)
            del_idx = int(del_idx_str) - 1
            if 0 <= del_idx < len(current_items):
                deleted_item_name = current_items.pop(del_idx).get('name', 'Unknown item')
                print(f"'{deleted_item_name}' deleted.")
            else: print("Invalid number.")
        except (ValueError, TypeError): print("Invalid input.")

    def _get_teacher_details(self, defaults=None):
        defaults = defaults or {}
        name = self.get_input_with_default(None, "Teacher Name", str, lambda x: len(x) > 0, default_value_override=defaults.get('name'))
        qualifications = defaults.get('qualifications', [])
        
        print(f"Enter qualified subjects for {name} (comma-separated numbers or names):")
        while True:
            for i, subj in enumerate(QUALIFIABLE_SUBJECTS): print(f"  {i+1}. {subj}{' (current)' if subj in qualifications else ''}")
            q_input = input("Add qualifications (or 'done'): ").strip()
            if q_input.lower() == 'done': break
            for q_part in q_input.split(','):
                q_clean = q_part.strip()
                if not q_clean: continue
                matched_subj = None
                try: 
                    idx = int(q_clean) - 1
                    if 0 <= idx < len(QUALIFIABLE_SUBJECTS): matched_subj = QUALIFIABLE_SUBJECTS[idx]
                except ValueError:
                    matched_subj = next((s for s in QUALIFIABLE_SUBJECTS if s.lower() == q_clean.lower()), None)
                if matched_subj and matched_subj not in qualifications:
                    qualifications.append(matched_subj)
        
        num_p_day = self.engine.get_parameters().get('num_periods_per_day', 1)
        availability_str = self.get_input_with_default(None, f"Availability for {name} (blank=always, e.g., 'Unavailable Mon P1-P2')", str, allow_empty=True, default_value_override=defaults.get('raw_availability_str'))
        
        return {'name': name, 'qualifications': qualifications, 'availability': parse_teacher_availability(availability_str, num_p_day), 'raw_availability_str': availability_str}

    def _get_elementary_subject_details(self, defaults=None):
        defaults = defaults or {}
        name = self.get_input_with_default(None, "Subject Name", str, lambda x:len(x)>0, default_value_override=defaults.get('name'))
        periods = self.get_input_with_default(None, f"Periods/week for {name}", int, lambda x:x>0, default_value_override=defaults.get('periods_per_week'))
        constraints = self.get_input_with_default(None, "Scheduling constraints (e.g., 'NOT P1')", str, allow_empty=True, default_value_override=defaults.get('scheduling_constraints_raw'))
        subj_area = self.get_input_with_default(None, f"Categorize '{name}' as", str, choices=QUALIFIABLE_SUBJECTS, default_value_override=defaults.get('subject_area', name))
        num_p_day = self.engine.get_parameters().get('num_periods_per_day', 1)
        return {'name': name, 'periods_per_week': periods, 'assigned_teacher_name': None, 'subject_area': subj_area, 'scheduling_constraints_raw': constraints, 'parsed_constraints': parse_scheduling_constraint(constraints, num_p_day)}

    def get_high_school_courses(self):
        print("\n--- High School Course Management ---")
        hs_db = copy.deepcopy(self.session_cache.get('high_school_credits_db', HIGH_SCHOOL_COURSE_CREDITS_TEMPLATE))
        if self.get_input_with_default('modify_credit_db_choice', "Modify course credit DB?", str, choices=['yes','no']).lower() == 'yes':
            while True:
                c_name = input("Course name to add/modify (or 'done'): ").strip()
                if c_name.lower() == 'done': break
                if not c_name: continue
                try:
                    c_cred = int(input(f"Credits for {c_name}: "))
                    hs_db[c_name] = c_cred
                except ValueError: print("Invalid number.")
        self.session_cache['high_school_credits_db'] = hs_db
        self.engine.set_hs_credits_db(hs_db)
        
        # This now includes the complex suggestion workflow
        defined_courses = self._get_list_data('courses_data_raw_input', 'course/block', 'courses/blocks', self._get_high_school_course_details)
        
        # Handle 1-credit course grouping
        one_credit_courses = [c for c in defined_courses if c.get('_is_one_credit_buffer_item')]
        final_courses = [c for c in defined_courses if not c.get('_is_one_credit_buffer_item')]

        while one_credit_courses:
            print("\n--- 1-Credit Course Grouping ---")
            print("Remaining 1-credit courses to group:");
            for idx, c in enumerate(one_credit_courses): print(f"  {idx+1}. {c['name']}")
            if self.get_input_with_default(None, "Group some now?", str, choices=['yes', 'no']).lower() != 'yes': break
            
            indices_str = self.get_input_with_default(None, "Select courses by number to group (comma-separated)", str)
            try:
                selected_indices = [int(x.strip())-1 for x in indices_str.split(',')]
                if not all(0 <= i < len(one_credit_courses) for i in selected_indices) or len(set(selected_indices)) < 2:
                    print("Invalid selection. Must be valid numbers and at least 2 unique courses."); continue
                
                courses_to_group = [one_credit_courses[i] for i in selected_indices]
                block_name = self.get_input_with_default(None, "Name for this new block", str, lambda x: len(x)>0)
                
                # Create a new course block from the grouped 1-credit courses
                # This is a simplified version; for full logic, call another details-gathering function
                new_block = self._get_high_school_course_details(defaults={'name': block_name, 'credits': len(courses_to_group)})
                if new_block:
                    new_block['name'] = f"{block_name} (contains: {', '.join(c['name'] for c in courses_to_group)})"
                    final_courses.append(new_block)
                
                # Remove grouped courses from the list
                for i in sorted(selected_indices, reverse=True):
                    one_credit_courses.pop(i)
            except ValueError: print("Invalid input.")

        if one_credit_courses:
            print(f"WARNING: {len(one_credit_courses)} 1-credit courses remain ungrouped and will be ignored.")

        return final_courses

    def _add_courses_from_template(self, current_courses):
        newly_added_courses = []
        hs_db = self.engine.high_school_credits_db
        print("\n--- Add Courses from Template ---")

        while True:
            current_names = {c['name'].split(' (')[0].strip() for c in current_courses}
            available = [(name, creds) for name, creds in sorted(hs_db.items()) if name not in current_names]
            if not available:
                print("All courses from the template have been added to the list."); break

            for idx, (name, creds) in enumerate(available): print(f"  {idx+1:2d}. {name} ({creds} credits)")
            selection = input("Enter numbers of courses to add (comma-separated, or 'done'): ").strip()
            if selection.lower() == 'done': break

            try:
                indices = [int(x.strip()) - 1 for x in selection.split(',')]
                for index in sorted(list(set(indices))):
                    if 0 <= index < len(available):
                        name, credits = available[index]
                        print(f"\n-- Configuring '{name}' --")
                        new_course = self._get_high_school_course_details(defaults={'name': name, 'credits': credits})
                        if new_course: newly_added_courses.append(new_course)
            except ValueError: print("Invalid input.")
        return newly_added_courses
        
    def _get_high_school_course_details(self, defaults=None):
        params = self.engine.get_parameters()
        num_p_day = params.get('num_periods_per_day', 1)
        p_dur_min = params.get('period_duration_minutes', 60)
        weeks_course_dur = params.get('weeks_per_term', 18)
        if params.get('scheduling_model') == "Full Year":
            weeks_course_dur = params.get('num_instructional_weeks', 36)

        defaults = defaults or {}
        name = self.get_input_with_default(None, "Course Name", str, lambda x: len(x) > 0, default_value_override=defaults.get('name'))
        
        credits_from_db = self.engine.high_school_credits_db.get(name)
        credits = self.get_input_with_default(None, f"Credits for {name}", int, lambda x: x > 0, default_value_override=defaults.get('credits', credits_from_db))
        
        if credits == 1 and not defaults.get('name', '').startswith("Suggested"):
            print("INFO: 1-credit courses will be grouped later.")
            # Simplified details for 1-credit courses initially
            subj_area = self.get_input_with_default(None, f"Subject area for '{name}'", str, choices=QUALIFIABLE_SUBJECTS, default_value_override=defaults.get('subject_area'))
            grade_str = self.get_input_with_default(None, f"Grade Level for {name} (10, 11, 12, Mixed)", str, default_value_override=str(defaults.get('grade_level', '10')))
            grade = "Mixed" if grade_str.lower() == "mixed" else (int(grade_str) if grade_str.isdigit() else "Mixed")
            return {'name': name, 'credits': 1, 'subject_area': subj_area, 'grade_level': grade, '_is_one_credit_buffer_item': True}

        grade_str = self.get_input_with_default(None, f"Grade Level for {name} (10, 11, 12, Mixed)", str, default_value_override=str(defaults.get('grade_level', '10')))
        grade = "Mixed" if grade_str.lower() == "mixed" else (int(grade_str) if grade_str.isdigit() else "Mixed")
        subj_area = self.get_input_with_default(None, f"Subject area for '{name}'", str, choices=QUALIFIABLE_SUBJECTS, default_value_override=defaults.get('subject_area'))

        course_mins = credits * CREDITS_TO_HOURS_PER_CREDIT * 60
        periods_year = math.ceil(course_mins / p_dur_min) if p_dur_min > 0 else 0
        periods_week = math.ceil(periods_year / weeks_course_dur) if weeks_course_dur > 0 else 0
        periods_week = max(1, periods_week)
        print(f"  INFO: Calculated {periods_week} periods/week for this course.")

        raw_constr = self.get_input_with_default(None, f"Constraints for {name} (e.g., 'NOT P1')", str, allow_empty=True, default_value_override=defaults.get('scheduling_constraints_raw'))
        parsed_constr = parse_scheduling_constraint(raw_constr, num_p_day)
        
        term = defaults.get('term_assignment', 1)
        if params.get('num_terms', 1) > 1:
            term = self.get_input_with_default(None, f"Assign to term (1-{params['num_terms']})", int, lambda x: 1 <= x <= params['num_terms'], default_value_override=term)
        
        return {'name': name, 'credits': credits, 'grade_level': grade, 'subject_area': subj_area, 
                'assigned_teacher_name': None, 'periods_per_week_in_active_term': periods_week, 'scheduling_constraints_raw': raw_constr,
                'parsed_constraints': parsed_constr, 'term_assignment': term, '_is_one_credit_buffer_item': False}

    def _get_single_cohort_constraint_details(self, defaults=None):
        all_course_names = [c['name'].split(' (')[0].strip() for c in self.engine.courses_data]
        if not all_course_names: print("No courses defined yet."); return None
        print("\nAvailable courses for cohort constraints:")
        for i, name in enumerate(all_course_names): print(f"  {i+1}. {name}")
        
        while True:
            clash_str = self.get_input_with_default(None, "Enter clashing courses (comma-separated names/numbers, >=2)", str)
            if not clash_str: return None
            
            selected_names = []
            valid = True
            for item in clash_str.split(','):
                item = item.strip()
                try: 
                    idx = int(item) - 1
                    if 0 <= idx < len(all_course_names):
                        selected_names.append(all_course_names[idx])
                    else:
                        print(f"Invalid number: {item}"); valid=False; break
                except ValueError:
                    matched = next((cn for cn in all_course_names if item.lower() == cn.lower()), None)
                    if matched: selected_names.append(matched)
                    else: print(f"Could not find course: {item}"); valid=False; break
            
            if valid and len(set(selected_names)) >= 2:
                return list(set(selected_names))
            elif valid:
                print("Constraint requires at least two different courses.")

    def _calculate_period_times_for_display(self):
        params = self.engine.get_parameters()
        if 'period_times_minutes' in params and params['period_times_minutes']:
            return [f"{format_time_from_minutes(s)}-{format_time_from_minutes(e)}" for s, e in params['period_times_minutes']]
        return [f"P{i+1}" for i in range(params.get('num_periods_per_day', 1))]

    def display_schedules_console(self):
        schedules_details = self.engine.get_generated_schedules()
        params = self.engine.get_parameters()
        period_times = self._calculate_period_times_for_display()
        num_p, num_tracks = params.get('num_periods_per_day',1), params.get('num_concurrent_tracks_per_period',1)

        for sched_detail in schedules_details:
            s_id, schedule = sched_detail['id'], sched_detail['schedule']
            print(f"\n\n--- TIMETABLE - SCHEDULE ID: {s_id} ---")
            if s_id == "Best_Failed_Attempt" and 'metrics' in sched_detail:
                metrics = sched_detail['metrics']
                print(f"  (Failed Attempt: Placed {metrics['overall_completion_rate']*100:.2f}%, Unmet Grade Slots: {metrics['unmet_grade_slots_count']}, Insufficient Prep: {metrics['unmet_prep_teachers_count']})")

            for term_idx, term_data in schedule.items():
                print(f"\n--- Term {term_idx} (Sched ID: {s_id}) ---")
                header = ["Period/Time"] + DAYS_OF_WEEK
                table_data = [header]
                for p_idx in range(num_p):
                    p_label = f"P{p_idx+1}"
                    if p_idx < len(period_times): p_label += f"\n{period_times[p_idx]}"
                    row_content = [p_label]
                    for day in DAYS_OF_WEEK:
                        cell_entries = []
                        for track_idx in range(num_tracks):
                            entry = term_data[day][p_idx][track_idx]
                            trk_lab = f"[Trk{track_idx+1}] " if num_tracks > 1 else ""
                            if entry and entry[0]:
                                cell_entries.append(f"{trk_lab}{entry[0][:25]}\n({entry[1][:10] if entry[1] else 'No T.'})")
                            else: cell_entries.append(f"{trk_lab}---")
                        row_content.append("\n---\n".join(cell_entries).replace(" / ", "/\n"))
                    table_data.append(row_content)
                
                if tabulate: print(tabulate(table_data, headers="firstrow", tablefmt="grid"))
                else: [print(" | ".join(map(str, row))) for row in table_data]

    def export_schedules_pdf(self):
        schedules_details = self.engine.get_generated_schedules()
        params = self.engine.get_parameters()
        safe_name = "".join(x for x in params.get('school_name', 'School') if x.isalnum())
        final_fn = f"{safe_name}_Schedules_{datetime.date.today():%Y-%m-%d}.pdf"

        try:
            doc = SimpleDocTemplate(final_fn, pagesize=landscape(letter))
            styles, story = getSampleStyleSheet(), []
            period_times_pdf = self._calculate_period_times_for_display()
            num_p, num_tracks = params.get('num_periods_per_day',1), params.get('num_concurrent_tracks_per_period',1)

            for i, sched_detail in enumerate(schedules_details):
                s_id, schedule = sched_detail['id'], sched_detail['schedule']
                story.append(Paragraph(f"Master Schedule - {params.get('school_name', 'N/A')} (ID: {s_id})", styles['h1']))
                story.append(Spacer(1, 12))

                for term_idx, term_data in schedule.items():
                    story.append(Paragraph(f"Term {term_idx}", styles['h2']))
                    pdf_data = [[Paragraph(f"<b>Period/Time</b>", styles['Normal'])] + [Paragraph(f"<b>{d}</b>", styles['Normal']) for d in DAYS_OF_WEEK]]
                    for p_idx in range(num_p):
                        p_label = f"<b>P{p_idx+1}</b>"
                        if p_idx < len(period_times_pdf): p_label += f"<br/>{period_times_pdf[p_idx]}"
                        row_pdf = [Paragraph(p_label, styles['Normal'])]
                        for day in DAYS_OF_WEEK:
                            cell_paras = []
                            for track_idx in range(num_tracks):
                                entry = term_data[day][p_idx][track_idx]
                                trk_lab = f"<i>Trk{track_idx+1}:</i> " if num_tracks > 1 else ""
                                if entry and entry[0]:
                                    entry_name = entry[0].replace(" / ", "<br/>")
                                    cell_paras.append(Paragraph(f"{trk_lab}{entry_name}<br/>({entry[1] if entry[1] else 'No T.'})", styles['Normal']))
                                else: cell_paras.append(Paragraph(f"{trk_lab}---", styles['Normal']))
                            row_pdf.append(cell_paras)
                        pdf_data.append(row_pdf)
                    
                    pw, _ = landscape(letter); aw = pw - 1.5 * 72
                    col_w = [aw * 0.15] + [(aw * 0.85) / len(DAYS_OF_WEEK)] * len(DAYS_OF_WEEK)
                    table = Table(pdf_data, colWidths=col_w, repeatRows=1)
                    table.setStyle(TableStyle([
                        ('BACKGROUND',(0,0),(-1,0),colors.lightgrey), 
                        ('GRID',(0,0),(-1,-1),0.5,colors.black), 
                        ('VALIGN',(0,0),(-1,-1),'MIDDLE'), 
                        ('ALIGN',(0,0),(-1,-1),'CENTER'),
                        ('FONTSIZE', (0,0), (-1,-1), 7)
                    ]))
                    story.append(table)
                    story.append(Spacer(1, 24))
                if i < len(schedules_details) - 1: story.append(PageBreak())
            
            doc.build(story)
            print(f"\nSUCCESS: Schedule(s) exported to {final_fn}")
        except Exception as e:
            print(f"\nERROR: PDF export failed: {e}")
            traceback.print_exc()

    def _load_session_cache(self):
        try:
            if os.path.exists("scheduler_session_cache.tmp"):
                with open("scheduler_session_cache.tmp", "r") as f:
                    self.session_cache = json.load(f)
                print("INFO: Loaded previous session data.")
                # Populate engine with cached data
                if 'params' in self.session_cache:
                    # Convert date/time strings back to objects
                    params = self.session_cache['params']
                    for key in ['start_date', 'end_date']:
                        if key in params and params[key]: params[key] = parse_date(params[key])
                    for key in ['school_start_time', 'school_end_time', 'lunch_start_time', 'lunch_end_time']:
                         if key in params and params[key]: params[key] = parse_time(params[key])
                    self.engine.set_parameters(params)
                if 'high_school_credits_db' in self.session_cache:
                    self.engine.set_hs_credits_db(self.session_cache['high_school_credits_db'])
        except (json.JSONDecodeError, IOError, TypeError) as e:
            print(f"WARN: Could not load session cache ({e}). Starting fresh.")
            self.session_cache = {}

    def _save_session_cache(self):
        try:
            # Add final engine parameters and data to cache before saving
            self.session_cache['params'] = self.engine.get_parameters()
            self.session_cache['high_school_credits_db'] = self.engine.high_school_credits_db
            
            def default_serializer(o):
                if isinstance(o, (datetime.date, datetime.time)): return o.isoformat()
                raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")

            with open("scheduler_session_cache.tmp", "w") as f:
                json.dump(self.session_cache, f, indent=2, default=default_serializer)
            print("INFO: Current input parameters saved to session cache.")
        except Exception as e:
            print(f"WARNING: Could not save session cache: {e}")

# Add the project root to the Python path to resolve imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from gui.gui_app import run_app

if __name__ == "__main__":
    # The application is now launched through the GUI.
    # The ConsoleUIController is no longer used.
    run_app()