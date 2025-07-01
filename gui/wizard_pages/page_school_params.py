from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLineEdit,
                             QComboBox, QDateEdit, QTimeEdit, QLabel,
                             QGroupBox, QHBoxLayout, QCheckBox)
from PyQt6.QtCore import QDate, QTime
import math
from gui.scheduler_engine import calculate_instructional_days, parse_date

class PageSchoolParams(QWidget):
    def __init__(self, data_handler):
        super().__init__()
        self.data_handler = data_handler

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.school_type_combo = QComboBox()
        self.school_type_combo.addItems(["High School", "Elementary"])

        self.school_name_input = QLineEdit()
        self.start_date_input = QDateEdit(calendarPopup=True)
        self.end_date_input = QDateEdit(calendarPopup=True)
        self.start_time_input = QTimeEdit()

        self.start_date_input.setDate(QDate.currentDate().addYears(1).addMonths(-4)) # Sensible default
        self.end_date_input.setDate(QDate.currentDate().addYears(1).addMonths(2)) # Sensible default
        self.start_time_input.setTime(QTime(8, 30))

        form_layout.addRow("School Type:", self.school_type_combo)
        form_layout.addRow("School Name:", self.school_name_input)
        form_layout.addRow("School Year Start Date:", self.start_date_input)
        form_layout.addRow("School Year End Date:", self.end_date_input)
        form_layout.addRow("Daily School Start Time:", self.start_time_input)

        layout.addWidget(QLabel("<b>Step 1: School Parameters</b>"))
        layout.addLayout(form_layout)
        layout.addStretch()

        self.setLayout(layout)

        self.data_handler.data_loaded.connect(self.load_data)

    def load_data(self):
        """Loads data from the data_handler into the widgets."""
        params = self.data_handler.get_value('params', {})
        
        school_type = params.get('school_type', 'High School')
        self.school_type_combo.setCurrentText(school_type)
        
        self.school_name_input.setText(params.get('school_name', ''))
        
        start_date_str = params.get('start_date_str')
        if start_date_str:
            self.start_date_input.setDate(QDate.fromString(start_date_str, "yyyy-MM-dd"))
        
        end_date_str = params.get('end_date_str')
        if end_date_str:
            self.end_date_input.setDate(QDate.fromString(end_date_str, "yyyy-MM-dd"))

        start_time_str = params.get('start_time_str')
        if start_time_str:
            self.start_time_input.setTime(QTime.fromString(start_time_str, "h:mm AP"))

    def save_data(self):
        """Saves the current widget states to the data_handler."""
        # Fetch the most recent params dictionary to update it
        params = self.data_handler.get_value('params', {})
        
        params['school_type'] = self.school_type_combo.currentText()
        params['school_name'] = self.school_name_input.text()
        params['start_date_str'] = self.start_date_input.date().toString("yyyy-MM-dd")
        params['end_date_str'] = self.end_date_input.date().toString("yyyy-MM-dd")
        params['start_time_str'] = self.start_time_input.time().toString("h:mm AP")
        
        # Perform crucial calculations for later steps
        start_date = parse_date(params['start_date_str'])
        end_date = parse_date(params['end_date_str'])
        num_id = calculate_instructional_days(start_date, end_date, params.get('non_instructional_days_str', ''))
        params['instructional_days'] = num_id
        params['num_instructional_weeks'] = math.ceil(num_id / 5) if num_id > 0 else 0

        self.data_handler.set_value('params', params)
        print(f"Saved School Params. num_instructional_weeks = {params['num_instructional_weeks']}")