from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QProgressBar, QTextEdit, QLabel)
from PyQt6.QtCore import QThread, pyqtSignal, QObject

from gui.scheduler_engine import SchedulingEngine

class SchedulerThread(QThread):
    progress_updated = pyqtSignal(int, str)
    finished = pyqtSignal()

    def __init__(self, engine, num_schedules, max_attempts):
        super().__init__()
        self.engine = engine
        self.num_schedules = num_schedules
        self.max_attempts = max_attempts

    def run(self):
        """Run the scheduling engine in the background."""
        self.progress_updated.emit(10, "Starting engine...")
        
        success = self.engine.generate_schedules(self.num_schedules, self.max_attempts)
        
        self.progress_updated.emit(90, "Finalizing schedules...")
        self.progress_updated.emit(100, "Done.")
        self.finished.emit()

class PageRun(QWidget):
    scheduler_finished = pyqtSignal()
    force_save_all_data_signal = pyqtSignal() # <--- ADD THIS SIGNAL

    def __init__(self, data_handler, engine):
        super().__init__()
        self.data_handler = data_handler
        self.engine = engine

        layout = QVBoxLayout(self)
        
        self.run_button = QPushButton("Run Scheduler")
        self.run_button.clicked.connect(self.run_scheduler)

        self.progress_bar = QProgressBar()
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)

        layout.addWidget(QLabel("<b>Step 5: Run Scheduler</b>"))
        layout.addWidget(self.run_button)
        layout.addWidget(self.progress_bar)
        layout.addWidget(QLabel("Log:"))
        layout.addWidget(self.log_view)
        
        self.setLayout(layout)

    def run_scheduler(self):
        self.run_button.setEnabled(False)
        self.log_view.clear()
        
        # Emit the signal to tell the main window to save everything.
        self.force_save_all_data_signal.emit()
        
        # Now, the data handler will be up-to-date when we set the engine params.
        self.engine.set_parameters(self.data_handler.get_value('params', {}))
        self.engine.set_teachers(self.data_handler.get_value('teachers_data', []))
        self.engine.set_courses(self.data_handler.get_value('courses_data_raw_input', []))
        self.engine.set_cohort_constraints(self.data_handler.get_value('cohort_constraints', []))

        # These would be configurable in a more advanced UI
        num_schedules = 1
        max_attempts = 200

        self.thread = SchedulerThread(self.engine, num_schedules, max_attempts)
        self.thread.progress_updated.connect(self.update_progress)
        self.thread.finished.connect(self.on_scheduler_done)
        self.thread.start()

    def update_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.log_view.append(message)

    def on_scheduler_done(self):
        """This slot is called when the background thread is finished."""
        self.run_button.setEnabled(True)
        self.progress_bar.setValue(100)

        final_schedules = self.engine.get_generated_schedules()
        if final_schedules:
            self.log_view.append("\n--- Scheduling Successful! ---")
            self.log_view.append(f"Generated {len(final_schedules)} valid schedule(s).")
        else:
            self.log_view.append("\n--- Scheduling Failed ---")
            self.log_view.append("No valid schedules were generated.")
        
        self.log_view.append("\n--- Full Engine Log ---")
        self.log_view.setText(self.log_view.toPlainText() + "\n" + "\n".join(self.engine.get_run_log()))
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

        self.scheduler_finished.emit()