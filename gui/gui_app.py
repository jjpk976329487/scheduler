import sys
import re # Added import for regex
from PyQt6.QtWidgets import (QApplication, QMainWindow, QStackedWidget, QPushButton,
                             QVBoxLayout, QWidget, QHBoxLayout, QMenuBar, QFileDialog, QMessageBox, QDialog)
from collections import defaultdict
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction

from gui.data_handler import DataHandler
from gui.scheduler_engine import SchedulingEngine

# Import wizard pages
from gui.wizard_pages.page_school_params import PageSchoolParams
from gui.wizard_pages.page_schedule_structure import PageScheduleStructure
from gui.wizard_pages.page_teachers import PageTeachers
from gui.wizard_pages.page_courses import PageCourses, CourseStreamSelectionDialog # Changed import to new dialog
from gui.wizard_pages.page_run import PageRun
from gui.wizard_pages.page_results import PageResults
def group_suggestions_by_subject(suggestions):
    """
    Groups a flat list of course suggestions by their base name using a regex.
    This is more robust for names like "Social Studies 30-1".
    """
    grouped = defaultdict(list)
    # This regex looks for a name, optional whitespace, a hyphen, optional whitespace, and then 1 or 2 digits at the end.
    stream_pattern = re.compile(r'(.+?)\s*-\s*(\d{1,2})$')

    for course in suggestions:
        match = stream_pattern.match(course['name'])
        if match:
            # If it's a stream course (e.g., "Math 30-1"), use the base name as the key
            base_name = match.group(1).strip()
            grouped[base_name].append(course)
        else:
            # If it's not a stream course (e.g., "Legal Studies", "Phys-Ed 10"), use its own name as the key
            grouped[course['name']].append(course)
        
    # You can add a print here for debugging
    print(f"DEBUG: Grouped suggestions into these keys: {list(grouped.keys())}")
    return dict(grouped)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("School Scheduler Wizard")
        self.setGeometry(100, 100, 900, 700)

        self.data_handler = DataHandler()
        self.engine = SchedulingEngine()
        self.stacked_widget = QStackedWidget()
        
        # Create and add pages
        self.pages = [
            PageSchoolParams(self.data_handler),
            PageScheduleStructure(self.data_handler),
            PageTeachers(self.data_handler),
            PageCourses(self.data_handler, self.engine), # Store a reference to the courses page
            PageRun(self.data_handler, self.engine),
            PageResults(self.data_handler, self.engine)
        ]
        for page in self.pages:
            self.stacked_widget.addWidget(page)

        # Navigation buttons
        self.back_button = QPushButton("Back")
        self.next_button = QPushButton("Next")
        self.back_button.clicked.connect(self.go_to_previous_page)
        self.next_button.clicked.connect(self.go_to_next_page)

        nav_layout = QHBoxLayout()
        nav_layout.addStretch()
        nav_layout.addWidget(self.back_button)
        nav_layout.addWidget(self.next_button)

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.stacked_widget)
        main_layout.addLayout(nav_layout)

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        self._create_menu_bar()
        self.update_navigation()

    def _create_menu_bar(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")

        save_action = QAction("&Save Session", self)
        save_action.triggered.connect(self.save_session)
        file_menu.addAction(save_action)

        load_action = QAction("&Load Session", self)
        load_action.triggered.connect(self.load_session)
        file_menu.addAction(load_action)

        # Connect signals from the run page to the results page
        self.pages[4].scheduler_finished.connect(self.pages[5].display_schedules)
        self.pages[4].scheduler_finished.connect(lambda: self.stacked_widget.setCurrentIndex(5))
        
        # Connect the suggestion_requested signal from PageCourses
        # Assuming PageCourses is the 4th page (index 3)
        self.courses_page = self.pages[3]
        self.courses_page.suggestion_requested.connect(self.handle_suggestion_request)
        
        # Connect the force_save_all_data_signal from PageRun to MainWindow's save_all_page_data method
        self.pages[4].force_save_all_data_signal.connect(self.save_all_page_data)

    def go_to_next_page(self):
        current_index = self.stacked_widget.currentIndex()
        if 0 <= current_index < len(self.pages):
            # Save data from the current page before proceeding
            if hasattr(self.pages[current_index], 'save_data'):
                self.pages[current_index].save_data()

        if current_index < self.stacked_widget.count() - 1:
            self.stacked_widget.setCurrentIndex(current_index + 1)
            # Trigger UI setup or data load for the new page
            if hasattr(self.pages[current_index + 1], 'setup_ui_for_school_type'):
                 self.pages[current_index + 1].setup_ui_for_school_type()
            if hasattr(self.pages[current_index + 1], 'load_data'):
                 self.pages[current_index + 1].load_data()

        self.update_navigation()

    def go_to_previous_page(self):
        current_index = self.stacked_widget.currentIndex()
        if current_index > 0:
            self.stacked_widget.setCurrentIndex(current_index - 1)
        self.update_navigation()

    def update_navigation(self):
        current_index = self.stacked_widget.currentIndex()
        self.back_button.setEnabled(current_index > 0)
        self.next_button.setEnabled(current_index < self.stacked_widget.count() - 1)

    def save_session(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "Save Session", "", "JSON Files (*.json)")
        if filepath:
            success, message = self.data_handler.save_session(filepath)
            # Here you would show a status message to the user
            print(message)

    def load_session(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Load Session", "", "JSON Files (*.json)")
        if filepath:
            success, message = self.data_handler.load_session(filepath)
            # Here you would show a status message to the user
            print(message)

    def handle_suggestion_request(self):
        print("Suggestion requested. Saving all page data first.")
        self.save_all_page_data()

        # Synchronize Engine with FRESH data
        current_params = self.data_handler.get_value('params', {})
        current_teachers_data = self.data_handler.get_value('teachers_data', [])
        # --- START OF FIX ---
        # Get the course DB from the data handler and give it to the engine.
        # This is the missing step.
        credits_db = self.data_handler.get_value('high_school_credits_db', {})
        self.engine.set_hs_credits_db(credits_db)
        # --- END OF FIX ---
        
        self.engine.set_parameters(current_params)
        self.engine.set_teachers(current_teachers_data)
        
        current_courses = self.data_handler.get_value('courses_data_raw_input', [])
        
        # --- START OF MODIFIED LOGIC ---
        
        if not current_courses:
            # This is the "Initial Course Suggestions" flow
            try:
                suggestions = self.engine.suggest_core_courses()
            except Exception as e:
                QMessageBox.critical(self, "Engine Error", f"Failed to generate suggestions: {e}")
                return

            if not suggestions:
                QMessageBox.information(self, "No Suggestions", "The engine could not find any suggestions. Check teacher availability and qualifications.")
                return

            # Group the suggestions for the new dialog
            grouped_suggestions = group_suggestions_by_subject(suggestions)

            # Use the new, advanced dialog
            dialog = CourseStreamSelectionDialog(grouped_suggestions, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                selected_courses = dialog.get_selected_courses()
                if selected_courses:
                    current_courses.extend(selected_courses)
                    self.data_handler.set_value('courses_data_raw_input', current_courses)
                    # Refresh the UI on the courses page
                    self.courses_page.load_data()
        
        else:
            # This is the "Suggest Additional Courses" flow (for CTS, etc.)
            # This can remain simpler if these suggestions don't have streams.
            suggestions = self.engine.suggest_new_courses_from_capacity(current_courses)
            
            if not suggestions:
                QMessageBox.information(self, "No Suggestions", "The engine found no further capacity for new courses.")
                return

            # You can re-use the old, simpler dialog here if you want
            from gui.wizard_pages.page_courses import CourseSuggestionDialog # Re-import for this specific case
            dialog = CourseSuggestionDialog(
                "Suggest Additional Courses",
                "The engine has found capacity for additional CTS courses. Would you like to add these suggestions?",
                suggestions,
                parent=self
            )
            if dialog.exec() == QDialog.DialogCode.Accepted:
                current_courses.extend(suggestions)
                self.data_handler.set_value('courses_data_raw_input', current_courses)
                self.courses_page.load_data()

        # --- END OF MODIFIED LOGIC ---

    def save_all_page_data(self):
        """Iterates through all wizard pages and calls their save_data method."""
        print("MainWindow: Received signal to save all page data.")
        # Iterate through all pages up to (but not including) PageRun (index 4)
        for i in range(len(self.pages) - 2): # Exclude PageRun and PageResults
            page = self.pages[i]
            if hasattr(page, 'save_data'):
                page.save_data()


def run_app():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    run_app()