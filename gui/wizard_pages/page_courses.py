from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QTableWidget, QAbstractItemView,
                             QTableWidgetItem, QDialog, QLineEdit, QFormLayout, QTextEdit,
                             QDialogButtonBox, QComboBox, QSpinBox, QLabel, QMessageBox,
                             QScrollArea, QGroupBox, QCheckBox, QHBoxLayout) # Added new imports
from PyQt6.QtCore import Qt, pyqtSignal

from gui.scheduler_engine import QUALIFIABLE_SUBJECTS, HIGH_SCHOOL_COURSE_CREDITS_TEMPLATE, parse_scheduling_constraint
import math
from scheduler_engine import HIGH_SCHOOL_COURSE_CREDITS_TEMPLATE

class CourseDialog(QDialog):
    def __init__(self, course_data=None, engine=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add/Edit Course")
        self.engine = engine
        
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_input = QLineEdit()
        self.credits_spinbox = QSpinBox()
        self.credits_spinbox.setRange(0, 10)
        self.grade_level_combo = QComboBox()
        self.grade_level_combo.addItems(["10", "11", "12", "Mixed"])
        self.subject_area_combo = QComboBox()
        self.subject_area_combo.addItems(QUALIFIABLE_SUBJECTS)
        self.term_spinbox = QSpinBox()
        self.term_spinbox.setRange(1, 4)
        self.constraints_input = QLineEdit()
        self.constraints_input.setPlaceholderText("e.g., NOT P1; ASSIGN Mon P3")

        form.addRow("Course Name:", self.name_input)
        form.addRow("Credits:", self.credits_spinbox)
        form.addRow("Grade Level:", self.grade_level_combo)
        form.addRow("Subject Area:", self.subject_area_combo)
        form.addRow("Term Assignment:", self.term_spinbox)
        form.addRow("Constraints:", self.constraints_input)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        
        layout.addLayout(form)
        layout.addWidget(self.button_box)
        self.setLayout(layout)

        if course_data:
            self.name_input.setText(course_data.get('name', ''))
            self.credits_spinbox.setValue(course_data.get('credits', 0))
            self.grade_level_combo.setCurrentText(str(course_data.get('grade_level', 'Mixed')))
            self.subject_area_combo.setCurrentText(course_data.get('subject_area', ''))
            self.term_spinbox.setValue(course_data.get('term_assignment', 1))
            self.constraints_input.setText(course_data.get('scheduling_constraints_raw', ''))

    def get_data(self):
        # The GUI should only collect the raw data. The engine will do the calculation.
        return {
            'name': self.name_input.text(),
            'credits': self.credits_spinbox.value(),
            'grade_level': self.grade_level_combo.currentText(),
            'subject_area': self.subject_area_combo.currentText(),
            'term_assignment': self.term_spinbox.value(),
            'scheduling_constraints_raw': self.constraints_input.text(),
            '_is_one_credit_buffer_item': False
        }

class CourseSuggestionDialog(QDialog):
    def __init__(self, title, message, suggestions, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(400) # Ensure a reasonable minimum width
        self.setMinimumHeight(300) # Ensure a reasonable minimum height

        layout = QVBoxLayout(self)

        message_label = QLabel(message)
        message_label.setWordWrap(True) # Enable word wrapping for the message
        layout.addWidget(message_label)

        self.suggestion_text_edit = QTextEdit()
        self.suggestion_text_edit.setReadOnly(True)
        # Format suggestions for display
        suggestion_formatted_text = "\n".join([f"- {s['name']} (Term: {s['term_assignment']}, P/Wk: {s.get('periods_per_week_in_active_term')})" for s in suggestions])
        self.suggestion_text_edit.setText(suggestion_formatted_text)
        layout.addWidget(self.suggestion_text_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)
class CourseStreamSelectionDialog(QDialog):
    """
    A dialog that presents course suggestions grouped by subject,
    allowing the user to select which streams to add.
    """
    def __init__(self, grouped_courses, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Course Streams to Schedule")
        self.setGeometry(200, 200, 500, 600)

        self.checkboxes = [] # To store (checkbox, course_data) tuples

        # Main layout
        layout = QVBoxLayout(self)

        # Scroll Area for the list of courses
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(scroll_content)
        scroll_area.setWidget(scroll_content)

        # Populate the scroll area with course groups
        self._populate_courses(grouped_courses)

        # Buttons
        button_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.select_all)
        button_layout.addWidget(select_all_btn)
        button_layout.addStretch()
        
        # Standard OK/Cancel buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        button_layout.addWidget(self.button_box)

        layout.addLayout(button_layout)
        
    def _populate_courses(self, grouped_courses):
        """Fills the dialog with group boxes and checkboxes."""
        for base_name, streams in sorted(grouped_courses.items()):
            group_box = QGroupBox(base_name)
            group_layout = QVBoxLayout()

            for stream_course in streams:
                # The text on the checkbox is the full course name (e.g., "Math 10-1")
                checkbox = QCheckBox(stream_course['name'])
                group_layout.addWidget(checkbox)
                self.checkboxes.append((checkbox, stream_course)) # Store the checkbox and full data
            
            group_box.setLayout(group_layout)
            self.scroll_layout.addWidget(group_box)
        self.scroll_layout.addStretch()

    def select_all(self):
        """Checks all the checkboxes."""
        for checkbox, _ in self.checkboxes:
            checkbox.setChecked(True)

    def get_selected_courses(self):
        """Returns a list of the course data for all checked items."""
        selected = []
        for checkbox, course_data in self.checkboxes:
            if checkbox.isChecked():
                selected.append(course_data)
        return selected


class PageCourses(QWidget):
    suggestion_requested = pyqtSignal()

    def __init__(self, data_handler, engine):
        super().__init__()
        self.data_handler = data_handler
        self.engine = engine

        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)
        
        self.data_handler.data_loaded.connect(self.setup_ui_for_school_type)
        
    def setup_ui_for_school_type(self):
        # Clear existing widgets safely
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                # This handles nested layouts
                self.clear_layout(item.layout())

        params = self.data_handler.get_value('params', {})
        school_type = params.get('school_type', 'High School')

        if school_type == 'Elementary':
            self.setup_elementary_ui()
        else:
            self.setup_high_school_ui()

    def clear_layout(self, layout):
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                else:
                    self.clear_layout(item.layout())

    def setup_elementary_ui(self):
        self.layout.addWidget(QLabel("<b>Step 4: Manage Subjects</b>"))
        # Simplified UI for elementary subjects can be added here
        
    def setup_high_school_ui(self):
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Name", "Credits", "Grade", "Subject", "Term"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        self.add_button = QPushButton("Add Custom Course")
        self.template_button = QPushButton("Add from Template")
        self.suggest_button = QPushButton("Suggest Courses")
        self.edit_button = QPushButton("Edit Selected")
        self.delete_button = QPushButton("Delete Selected")

        self.add_button.clicked.connect(self.add_course)
        self.edit_button.clicked.connect(self.edit_course)
        self.delete_button.clicked.connect(self.delete_course)
        # self.template_button.clicked.connect(self.add_from_template)
        self.suggest_button.clicked.connect(self.suggest_courses)

        button_layout = QVBoxLayout()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.template_button)
        button_layout.addWidget(self.suggest_button)
        button_layout.addWidget(self.edit_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addStretch()

        main_layout = QVBoxLayout()
        main_layout.addWidget(QLabel("<b>Step 4: Manage Courses</b>"))
        main_layout.addWidget(self.table)
        main_layout.addLayout(button_layout)
        
        self.layout.addLayout(main_layout)
        self.load_data()

    def load_data(self):
        """Loads course data and ensures the credits DB is initialized."""
        params = self.data_handler.get_value('params', {})
        if params.get('school_type') != 'High School': return

        # --- START: NEW INITIALIZATION LOGIC ---
        # Check if the credits DB in the data_handler is empty
        credits_db = self.data_handler.get_value('high_school_credits_db')
        if not credits_db:
            print("Course DB is empty, initializing from template.")
            # If it's empty, load it from the engine's template
            credits_db = HIGH_SCHOOL_COURSE_CREDITS_TEMPLATE.copy()
            # And save it back to the data_handler for this session
            self.data_handler.set_value('high_school_credits_db', credits_db)
        # --- END: NEW INITIALIZATION LOGIC ---

        # Now, populate the UI from the raw course list
        courses = self.data_handler.get_value('courses_data_raw_input', [])
        self.table.setRowCount(len(courses))
        for row, course in enumerate(courses):
            self.table.setItem(row, 0, QTableWidgetItem(course.get('name', '')))
            self.table.setItem(row, 1, QTableWidgetItem(str(course.get('credits', ''))))
            self.table.setItem(row, 2, QTableWidgetItem(str(course.get('grade_level', ''))))
            self.table.setItem(row, 3, QTableWidgetItem(course.get('subject_area', '')))
            self.table.setItem(row, 4, QTableWidgetItem(str(course.get('term_assignment', ''))))
        self.table.resizeColumnsToContents()

    def save_data(self):
        pass

    def add_course(self):
        dialog = CourseDialog(engine=self.engine, parent=self)
        if dialog.exec():
            courses = self.data_handler.get_value('courses_data_raw_input', [])
            courses.append(dialog.get_data())
            self.data_handler.set_value('courses_data_raw_input', courses)
            self.load_data()
    
    def suggest_courses(self):
        self.suggestion_requested.emit()

    def edit_course(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows: return
        
        row_index = selected_rows[0].row()
        courses = self.data_handler.get_value('courses_data_raw_input', [])
        course_to_edit = courses[row_index]
        
        dialog = CourseDialog(course_data=course_to_edit, engine=self.engine, parent=self)
        if dialog.exec():
            courses[row_index] = dialog.get_data()
            self.data_handler.set_value('courses_data_raw_input', courses)
            self.load_data()

    def delete_course(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows: return
        
        row_index = selected_rows[0].row()
        courses = self.data_handler.get_value('courses_data_raw_input', [])
        courses.pop(row_index)
        self.data_handler.set_value('courses_data_raw_input', courses)
        self.load_data()