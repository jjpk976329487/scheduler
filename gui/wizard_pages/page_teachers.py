from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QTableWidget, QAbstractItemView,
                             QTableWidgetItem, QDialog, QLineEdit, QFormLayout,
                             QDialogButtonBox, QListWidget, QListWidgetItem, QLabel, QMessageBox)
from PyQt6.QtCore import Qt
from gui.scheduler_engine import QUALIFIABLE_SUBJECTS, parse_teacher_availability

# Your TeacherDialog class is fine, but I've added a small improvement
class TeacherDialog(QDialog):
    def __init__(self, teacher_data=None, num_periods=8, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add/Edit Teacher")
        
        self.num_periods = num_periods
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_input = QLineEdit()
        self.availability_input = QLineEdit()
        self.availability_input.setPlaceholderText("e.g., Unavailable Mon P1-P2; always available")
        
        self.qualifications_list = QListWidget()
        self.qualifications_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        for subj in QUALIFIABLE_SUBJECTS:
            item = QListWidgetItem(subj)
            self.qualifications_list.addItem(item)

        form.addRow("Name:", self.name_input)
        form.addRow("Qualifications:", self.qualifications_list)
        form.addRow("Availability:", self.availability_input)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        
        layout.addLayout(form)
        layout.addWidget(self.button_box)
        self.setLayout(layout)

        if teacher_data:
            self.name_input.setText(teacher_data.get('name', ''))
            self.availability_input.setText(teacher_data.get('raw_availability_str', 'always available')) # Use raw string here
            
            selected_quals = teacher_data.get('qualifications', [])
            for i in range(self.qualifications_list.count()):
                item = self.qualifications_list.item(i)
                if item.text() in selected_quals:
                    item.setSelected(True)

    def get_data(self):
        selected_qualifications = [item.text() for item in self.qualifications_list.selectedItems()]
        availability_str = self.availability_input.text()
        if not availability_str.strip(): # If user leaves it blank, default to always available
            availability_str = "always available"

        return {
            'name': self.name_input.text(),
            'qualifications': selected_qualifications,
            'raw_availability_str': availability_str, # Store the raw text for saving/re-editing
            # The 'availability' dictionary is now parsed in the save_data method
        }


class PageTeachers(QWidget):
    def __init__(self, data_handler):
        super().__init__()
        self.data_handler = data_handler
        layout = QVBoxLayout(self)
        
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Name", "Qualifications", "Availability"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        self.add_button = QPushButton("Add Teacher")
        self.edit_button = QPushButton("Edit Selected")
        self.delete_button = QPushButton("Delete Selected")

        self.add_button.clicked.connect(self.add_teacher)
        self.edit_button.clicked.connect(self.edit_teacher)
        self.delete_button.clicked.connect(self.delete_teacher)

        button_layout = QVBoxLayout()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.edit_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addStretch()

        main_layout = QVBoxLayout()
        main_layout.addWidget(QLabel("<b>Step 3: Manage Teachers</b>"))
        main_layout.addWidget(self.table)
        main_layout.addLayout(button_layout)
        layout.addLayout(main_layout)

        self.setLayout(layout)
        self.data_handler.data_loaded.connect(self.load_data)
        self.load_data()

    def load_data(self):
        teachers = self.data_handler.get_value('teachers_data', [])
        self.table.setRowCount(len(teachers))
        for row, teacher in enumerate(teachers):
            self.table.setItem(row, 0, QTableWidgetItem(teacher.get('name', '')))
            self.table.setItem(row, 1, QTableWidgetItem(", ".join(teacher.get('qualifications', []))))
            self.table.setItem(row, 2, QTableWidgetItem(teacher.get('raw_availability_str', 'always available')))
        self.table.resizeColumnsToContents()

    def save_data(self):
        """
        THIS IS THE FIX: This method ensures that the availability dictionary is
        correctly parsed for ALL teachers before the engine runs.
        """
        params = self.data_handler.get_value('params', {})
        num_periods = params.get('num_periods_per_day', 8)
        
        teachers = self.data_handler.get_value('teachers_data', [])
        
        for teacher in teachers:
            raw_text = teacher.get('raw_availability_str', 'always available')
            # Ensure even blank entries default to 'always available'
            if not raw_text or not raw_text.strip():
                raw_text = "always available"
            teacher['availability'] = parse_teacher_availability(raw_text, num_periods)
        
        self.data_handler.set_value('teachers_data', teachers)
        print("INFO: Refreshed and saved all teacher availability dictionaries.")

    def add_teacher(self):
        params = self.data_handler.get_value('params', {})
        num_periods = params.get('num_periods_per_day', 8)
        dialog = TeacherDialog(num_periods=num_periods, parent=self)
        if dialog.exec():
            new_data = dialog.get_data()
            if new_data['name']:
                teachers = self.data_handler.get_value('teachers_data', [])
                teachers.append(new_data)
                self.data_handler.set_value('teachers_data', teachers)
                self.load_data()

    def edit_teacher(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows: return
        
        row_index = selected_rows[0].row()
        teachers = self.data_handler.get_value('teachers_data', [])
        teacher_to_edit = teachers[row_index]

        params = self.data_handler.get_value('params', {})
        num_periods = params.get('num_periods_per_day', 8)
        dialog = TeacherDialog(teacher_data=teacher_to_edit, num_periods=num_periods, parent=self)
        
        if dialog.exec():
            teachers[row_index] = dialog.get_data()
            self.data_handler.set_value('teachers_data', teachers)
            self.load_data()

    def delete_teacher(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows: return
        
        reply = QMessageBox.question(self, 'Delete Teacher', 
                                     "Are you sure you want to delete the selected teacher(s)?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            for row_item in sorted(selected_rows, key=lambda item: item.row(), reverse=True):
                teachers = self.data_handler.get_value('teachers_data', [])
                teachers.pop(row_item.row())
                self.data_handler.set_value('teachers_data', teachers)
            self.load_data()