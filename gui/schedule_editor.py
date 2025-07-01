import copy

class ScheduleEditor:
    """
    This class contains all the business logic for validating and executing
    schedule modifications. It operates on a deep copy of the schedule
    to ensure that any changes are atomic and validated before being
    committed to the main application state.
    """

    def __init__(self, full_schedule_data: dict, courses_data: dict, student_group_assignments: dict):
        """
        Initializes the ScheduleEditor with the necessary data.

        Args:
            full_schedule_data (dict): The complete schedule data.
            courses_data (dict): A dictionary containing all course properties.
            student_group_assignments (dict): A mapping of course names to student groups.
        """
        self.schedule = copy.deepcopy(full_schedule_data)
        self.courses_data = courses_data
        self.student_group_assignments = student_group_assignments

    def get_valid_drop_targets(self, source_info: dict) -> list[tuple]:
        """
        Calculates all valid drop targets for a given source item by checking
        every slot in the schedule for validity.
        """
        valid_targets = []
        source_coords = (
            int(source_info['source_term']),
            source_info['source_day'],
            int(source_info['source_period']),
            int(source_info['source_track'])
        )
        source_course_name = source_info['course_name']
        source_credit_value = self.courses_data.get(source_course_name, {}).get('credits', 0)

        # Iterate through every potential slot in the entire schedule
        for term_str, days_data in self.schedule.items():
            term = int(term_str)
            for day, periods_list in days_data.items():
                if not isinstance(periods_list, list): continue
                for period_idx, tracks_list in enumerate(periods_list):
                    if not isinstance(tracks_list, list): continue
                    for track_idx, target_class_tuple in enumerate(tracks_list):
                        
                        target_coords = (term, day, period_idx, track_idx)

                        # 1. Don't allow dropping an item onto itself.
                        if source_coords == target_coords:
                            continue

                        target_class_info = None
                        if target_class_tuple and len(target_class_tuple) > 0 and target_class_tuple[0]:
                            target_class_info = {
                                'course_name': target_class_tuple[0],
                                'teacher_name': target_class_tuple[1]
                            }

                        # 2. If the target is OCCUPIED, check for credit parity for a valid SWAP.
                        # If credits don't match, it's not a valid swap target. Skip it.
                        if target_class_info:
                            target_course_name = target_class_info.get('course_name')
                            target_credit_value = self.courses_data.get(target_course_name, {}).get('credits', 0)
                            if source_credit_value != target_credit_value:
                                continue

                        # 3. Check for teacher conflicts. This handles both MOVE and SWAP scenarios.
                        if self._check_teacher_conflict(source_info, target_coords, target_class_info):
                            continue

                        # 4. Check for student group (cohort) conflicts. This also handles both MOVE and SWAP.
                        if self._check_student_group_conflict(source_info, target_coords, target_class_info):
                            continue
                        
                        # If all checks pass, this is a valid target.
                        valid_targets.append(target_coords)
                        
        return valid_targets

    def _is_teacher_busy(self, teacher: str, term: str, day: str, period_idx: int, exclude_track: int = None) -> bool:
        """Checks if a teacher is scheduled at a specific time, optionally excluding a track."""
        if not teacher: return False
        try:
            for track_idx, class_tuple in enumerate(self.schedule[term][day][period_idx]):
                if exclude_track is not None and track_idx == exclude_track:
                    continue
                if class_tuple and class_tuple[1] == teacher:
                    return True
        except (KeyError, IndexError):
            return False
        return False

    def _check_teacher_conflict(self, source_info: dict, target_coords: tuple, target_class_info: dict) -> bool:
        """Checks for teacher conflicts for a potential move or swap."""
        source_teacher = source_info['teacher_name']
        target_term, target_day, target_period, target_track = target_coords
        
        if self._is_teacher_busy(source_teacher, target_term, target_day, target_period, exclude_track=target_track):
            return True

        if target_class_info:
            target_teacher = target_class_info.get('teacher_name')
            source_term = source_info['source_term']
            source_day = source_info['source_day']
            source_period = source_info['source_period']
            source_track = source_info['source_track']
            if self._is_teacher_busy(target_teacher, source_term, source_day, source_period, exclude_track=source_track):
                return True
        
        return False

    def _are_student_groups_busy(self, student_groups: list, term: str, day: str, period_idx: int, exclude_track: int = None) -> bool:
        """Checks if any student group in a list is busy at a specific time."""
        if not student_groups: return False
        
        busy_groups = set()
        try:
            for track_idx, class_tuple in enumerate(self.schedule[term][day][period_idx]):
                if exclude_track is not None and track_idx == exclude_track:
                    continue
                if class_tuple and class_tuple[0]:
                    course_name = class_tuple[0]
                    groups_in_class = self.student_group_assignments.get(course_name, [])
                    for group in groups_in_class:
                        busy_groups.add(group)
        except (KeyError, IndexError):
            return False
        
        return not set(student_groups).isdisjoint(busy_groups)

    def _check_student_group_conflict(self, source_info: dict, target_coords: tuple, target_class_info: dict) -> bool:
        """Checks for student group conflicts for a potential move or swap."""
        source_course = source_info['course_name']
        source_groups = self.student_group_assignments.get(source_course, [])
        if not source_groups:
            return False

        target_term, target_day, target_period, target_track = target_coords
        
        if self._are_student_groups_busy(source_groups, target_term, target_day, target_period, exclude_track=target_track):
            return True

        if target_class_info:
            target_course = target_class_info.get('course_name')
            target_groups = self.student_group_assignments.get(target_course, [])
            if target_groups:
                source_term = source_info['source_term']
                source_day = source_info['source_day']
                source_period = source_info['source_period']
                source_track = source_info['source_track']
                if self._are_student_groups_busy(target_groups, source_term, source_day, source_period, exclude_track=source_track):
                    return True
        
        return False

    def perform_swap(self, source_info: dict, target_info: dict) -> tuple[bool, dict]:
        """
        Executes a move or swap operation on the internal schedule copy.

        Args:
            source_info (dict): Information about the source item.
            target_info (dict): Information about the target location.

        Returns:
            tuple[bool, dict]: A tuple containing a success flag and the modified schedule.
        """
        try:
            source_term = source_info['source_term']
            source_day = source_info['source_day']
            source_period = source_info['source_period']
            source_track = source_info['source_track']

            target_term = target_info['target_term']
            target_day = target_info['target_day']
            target_period = target_info['target_period']
            target_track = target_info['target_track']

            source_class_tuple = self.schedule[source_term][source_day][source_period][source_track]
            target_class_tuple = self.schedule[target_term][target_day][target_period][target_track]

            # Perform the swap
            self.schedule[target_term][target_day][target_period][target_track] = source_class_tuple
            self.schedule[source_term][source_day][source_period][source_track] = target_class_tuple

            return True, self.schedule
        except (KeyError, IndexError, TypeError) as e:
            print(f"Error during swap: {e}")
            return False, self.schedule