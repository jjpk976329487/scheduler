from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLineEdit,
                             QComboBox, QLabel, QSpinBox, QPushButton, QTextEdit, QCheckBox)
import math

class PageScheduleStructure(QWidget):
    def __init__(self, data_handler):
        super().__init__()
        self.data_handler = data_handler

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.scheduling_model_combo = QComboBox()
        self.scheduling_model_combo.addItems(["Semester", "Full Year", "Quarterly"])

        self.num_periods_spinbox = QSpinBox()
        self.num_periods_spinbox.setRange(1, 12)
        
        self.period_duration_spinbox = QSpinBox()
        self.period_duration_spinbox.setRange(10, 120)
        self.period_duration_spinbox.setValue(45)

        self.break_duration_spinbox = QSpinBox()
        self.break_duration_spinbox.setRange(0, 30)
        self.break_duration_spinbox.setValue(5)

        self.lunch_duration_spinbox = QSpinBox()
        self.lunch_duration_spinbox.setRange(0, 90)
        self.lunch_duration_spinbox.setValue(60)

        self.lunch_after_period_spinbox = QSpinBox()
        self.lunch_after_period_spinbox.setRange(1, 12)

        self.num_tracks_spinbox = QSpinBox()
        self.num_tracks_spinbox.setRange(1, 10)

        self.force_same_time_checkbox = QCheckBox("Force classes to be at the same time each day")

        self.preview_button = QPushButton("Preview Daily Timings")
        self.preview_button.clicked.connect(self.update_preview)
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)

        form_layout.addRow("Scheduling Model:", self.scheduling_model_combo)
        form_layout.addRow("Number of Periods per Day:", self.num_periods_spinbox)
        form_layout.addRow("Period Duration (minutes):", self.period_duration_spinbox)
        form_layout.addRow("Break Between Periods (minutes):", self.break_duration_spinbox)
        form_layout.addRow("Lunch Duration (minutes):", self.lunch_duration_spinbox)
        form_layout.addRow("Lunch After Period:", self.lunch_after_period_spinbox)
        form_layout.addRow("Concurrent Tracks per Period:", self.num_tracks_spinbox)
        form_layout.addRow(self.force_same_time_checkbox)
        
        layout.addWidget(QLabel("<b>Step 2: Schedule Structure</b>"))
        layout.addLayout(form_layout)
        layout.addWidget(self.preview_button)
        layout.addWidget(self.preview_text)
        layout.addStretch()

        self.setLayout(layout)

        self.data_handler.data_loaded.connect(self.load_data)

    def load_data(self):
        params = self.data_handler.get_value('params', {})
        self.scheduling_model_combo.setCurrentText(params.get('scheduling_model', 'Semester'))
        self.num_periods_spinbox.setValue(params.get('num_periods_per_day', 8))
        self.period_duration_spinbox.setValue(params.get('period_duration_minutes', 45))
        self.break_duration_spinbox.setValue(params.get('break_between_classes_minutes', 5))
        self.lunch_duration_spinbox.setValue(params.get('lunch_duration_minutes', 60))
        self.lunch_after_period_spinbox.setValue(params.get('lunch_after_period_num', 4))
        self.num_tracks_spinbox.setValue(params.get('num_concurrent_tracks_per_period', 1))
        self.force_same_time_checkbox.setChecked(params.get('force_same_time', True))

    def save_data(self):
        # CRITICAL FIX: Fetch the LATEST params dictionary from the DataHandler.
        # This dictionary now contains 'num_instructional_weeks' from PageSchoolParams.
        params = self.data_handler.get_value('params', {})
        
        model_choices_map = {"Quarterly": 4, "Semester": 2, "Full Year": 1}
        model_text = self.scheduling_model_combo.currentText()
        
        params['scheduling_model'] = model_text
        params['num_terms'] = model_choices_map.get(model_text, 1)
        params['num_periods_per_day'] = self.num_periods_spinbox.value()
        params['period_duration_minutes'] = self.period_duration_spinbox.value()
        params['break_between_classes_minutes'] = self.break_duration_spinbox.value()
        params['lunch_duration_minutes'] = self.lunch_duration_spinbox.value()
        params['lunch_after_period_num'] = self.lunch_after_period_spinbox.value()
        params['num_concurrent_tracks_per_period'] = self.num_tracks_spinbox.value()
        params['force_same_time'] = self.force_same_time_checkbox.isChecked()

        # Now this calculation will work correctly.
        num_iw = params.get('num_instructional_weeks', 0)
        num_t = params.get('num_terms', 1)
        
        if num_iw > 0 and num_t > 0:
            params['weeks_per_term'] = math.ceil(num_iw / num_t)
        else:
            params['weeks_per_term'] = 0 # Explicitly set to 0 if inputs are bad

        self.data_handler.set_value('params', params)
        print(f"Saved Schedule Structure. weeks_per_term = {params['weeks_per_term']}")

    def update_preview(self):
        # This is a simplified version of the logic from the original main.py
        # A more robust implementation would use the scheduler_engine if possible
        from gui.scheduler_engine import parse_time, time_to_minutes, format_time_from_minutes
        
        params = self.data_handler.get_value('params', {})
        start_time = parse_time(params.get('start_time_str', '8:30 AM'))
        if not start_time:
            self.preview_text.setText("Error: School start time is not set.")
            return

        num_p = self.num_periods_spinbox.value()
        p_dur = self.period_duration_spinbox.value()
        b_dur = self.break_duration_spinbox.value()
        lunch_dur = self.lunch_duration_spinbox.value()
        lunch_after_p = self.lunch_after_period_spinbox.value()

        current_m = time_to_minutes(start_time)
        preview = f"School Start: {format_time_from_minutes(current_m)}\n"

        for i in range(num_p):
            period_start_m = current_m
            period_end_m = current_m + p_dur
            preview += f"Period {i+1}: {format_time_from_minutes(period_start_m)} - {format_time_from_minutes(period_end_m)}\n"
            current_m = period_end_m
            if lunch_dur > 0 and (i + 1) == lunch_after_p:
                preview += f"  LUNCH:    {format_time_from_minutes(current_m)} - {format_time_from_minutes(current_m + lunch_dur)}\n"
                current_m += lunch_dur
            elif i < num_p - 1:
                preview += f"  Break:    {format_time_from_minutes(current_m)} - {format_time_from_minutes(current_m + b_dur)}\n"
                current_m += b_dur
        
        preview += f"School End: {format_time_from_minutes(current_m)}"
        self.preview_text.setText(preview)