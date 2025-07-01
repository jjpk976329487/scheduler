import json
from collections import defaultdict
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QTableWidget,
                             QTableWidgetItem, QLabel, QPushButton, QAbstractItemView)
from PyQt6.QtCore import Qt, QMimeData, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QDrag

from gui.scheduler_engine import DAYS_OF_WEEK, format_time_from_minutes
from gui.schedule_editor import ScheduleEditor

class ScheduleTableWidget(QTableWidget):
    schedule_updated = pyqtSignal(int, dict)

    def __init__(self, schedule_id, schedule_editor, cell_map, parent=None):
        super().__init__(parent)
        self.schedule_id = schedule_id
        self.schedule_editor = schedule_editor
        self.cell_map = cell_map
        self.highlighted_cells = []

        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setAcceptDrops(True)

    def startDrag(self, supportedActions):
        row = self.currentRow()
        col = self.currentColumn()
        item = self.item(row, col)

        if not item or not item.text().strip() or item.text().strip().endswith("---"):
            return

        term, day, period, track = self.cell_map.get((row, col))

        try:
            class_info_tuple = self.schedule_editor.schedule[term][day][period][track]
        except (KeyError, IndexError):
            return

        if not class_info_tuple or not class_info_tuple[0]:
            return

        source_info = {
            "source_term": term,
            "source_day": day,
            "source_period": period,
            "source_track": track,
            "course_name": class_info_tuple[0],
            "teacher_name": class_info_tuple[1],
        }

        mime_data = QMimeData()
        mime_data.setText(json.dumps(source_info))

        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec(supportedActions)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
            source_info_str = event.mimeData().text()
            source_info = json.loads(source_info_str)
            
            valid_targets = self.schedule_editor.get_valid_drop_targets(source_info)
            self._highlight_valid_targets(valid_targets)

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._clear_highlights()

    def dropEvent(self, event):
        if not event.mimeData().hasText():
            self._clear_highlights()
            return

        pos = event.position()
        target_row = self.rowAt(int(pos.y()))
        target_col = self.columnAt(int(pos.x()))

        target_coords = self.cell_map.get((target_row, target_col))
        if not target_coords:
            self._clear_highlights()
            return

        source_info = json.loads(event.mimeData().text())
        
        valid_targets = self.schedule_editor.get_valid_drop_targets(source_info)
        
        if target_coords not in valid_targets:
            self._clear_highlights()
            return
            
        target_info = {
            "target_term": target_coords[0],
            "target_day": target_coords[1],
            "target_period": target_coords[2],
            "target_track": target_coords[3],
        }

        success, new_schedule = self.schedule_editor.perform_swap(source_info, target_info)

        if success:
            event.acceptProposedAction()
            self.schedule_updated.emit(self.schedule_id, new_schedule)
        
        self._clear_highlights()

    def _highlight_valid_targets(self, valid_targets):
        self._clear_highlights()
        for row, col in self.cell_map:
            if self.cell_map[(row, col)] in valid_targets:
                item = self.item(row, col)
                if item:
                    item.setBackground(QColor("lightgreen"))
                    self.highlighted_cells.append(item)

    def _clear_highlights(self):
        for item in self.highlighted_cells:
            # Reset to default background
            item.setBackground(QBrush())
        self.highlighted_cells.clear()


class PageResults(QWidget):
    def __init__(self, data_handler, engine):
        super().__init__()
        self.data_handler = data_handler
        self.engine = engine
        self.schedules_data = {}

        layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        
        self.export_button = QPushButton("Export All to PDF")
        # self.export_button.clicked.connect(self.export_pdf)

        layout.addWidget(QLabel("<b>Step 6: View Schedules</b>"))
        layout.addWidget(self.tab_widget)
        layout.addWidget(self.export_button)
        self.setLayout(layout)

    def display_schedules(self):
        self.tab_widget.clear()
        self.tab_widget.addTab(QLabel("Processing results..."), "Loading")

        schedules = self.engine.get_generated_schedules()
        self.schedules_data = {s['id']: s for s in schedules}
        
        if not schedules:
            error_label = QLabel("Scheduling failed. No valid schedules were generated.")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            error_label.setStyleSheet("color: red; font-weight: bold;")
            self.tab_widget.clear()
            self.tab_widget.addTab(error_label, "Error")
            return
        
        self.tab_widget.clear() # Clear the "Processing results..." tab
        
        self.refresh_all_schedule_views()

    def refresh_all_schedule_views(self):
        self.tab_widget.clear()
        best_schedule_id = None
        if self.schedules_data:
            # Schedules are already sorted by score (best first) in scheduler_engine
            best_schedule_id = list(self.schedules_data.keys())[0]

        for s_id, sched_detail in self.schedules_data.items():
            tab_name = f"Schedule {s_id}"
            if s_id == best_schedule_id:
                tab_name += " (Best)"
            self.tab_widget.addTab(self._create_schedule_tab(s_id, sched_detail), tab_name)

    def _create_schedule_tab(self, s_id, sched_detail):
        schedule_data = sched_detail['schedule']
        metrics = sched_detail.get('metrics', {})
        
        main_layout = QVBoxLayout()
        term_tab_widget = QTabWidget()

        # Add metrics display
        metrics_label_text = f"Completion: {metrics.get('overall_completion_rate', 0)*100:.1f}% | G11 Core: {metrics.get('g11_core_count', 0)} | G12 Core: {metrics.get('g12_core_count', 0)}"
        if s_id == "Best_Failed_Attempt":
            metrics_label_text = f"FAILED ATTEMPT - Completion: {metrics.get('overall_completion_rate', 0)*100:.1f}% | Unmet Grade Slots: {metrics.get('unmet_grade_slots_count', 0)} | Insufficient Prep: {metrics.get('unmet_prep_teachers_count', 0)}"
        
        metrics_label = QLabel(metrics_label_text)
        metrics_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        metrics_label.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        main_layout.addWidget(metrics_label)
        main_layout.addWidget(term_tab_widget)


        courses_data_dict = {course['name']: course for course in self.engine.courses_data}
        
        student_group_assignments = defaultdict(list)
        for course in self.engine.courses_data:
            grade = course.get('grade_level')
            if grade:
                student_group_assignments[course['name']].append(f"Grade {grade} - Group A")


        schedule_editor = ScheduleEditor(
            full_schedule_data=schedule_data,
            courses_data=courses_data_dict,
            student_group_assignments=student_group_assignments
        )

        params = self.engine.get_parameters()
        period_times = self._calculate_period_times_for_display(params)
        num_p = params.get('num_periods_per_day', 1)
        num_tracks = params.get('num_concurrent_tracks_per_period', 1)

        for term_idx, term_data in schedule_data.items():
            cell_map = {}
            table = ScheduleTableWidget(s_id, schedule_editor, cell_map, self)
            table.schedule_updated.connect(self.handle_schedule_update)

            table.setColumnCount(len(DAYS_OF_WEEK))
            table.setHorizontalHeaderLabels(DAYS_OF_WEEK)
            
            num_separator_rows = num_p - 1 if num_p > 1 else 0
            table.setRowCount(num_p * num_tracks + num_separator_rows)

            v_header_labels = []
            row_cursor = 0
            for p_idx in range(num_p):
                for track_idx in range(num_tracks):
                    row = row_cursor + track_idx
                    p_label = f"P{p_idx+1}"
                    if num_tracks > 1:
                        p_label += f" / Trk{track_idx+1}"
                    if p_idx < len(period_times) and track_idx == 0:
                         p_label += f"\n{period_times[p_idx]}"
                    v_header_labels.append(p_label)
                
                if p_idx < num_p - 1:
                    v_header_labels.append("")

                for day_idx, day in enumerate(DAYS_OF_WEEK):
                    for track_idx in range(num_tracks):
                        row = row_cursor + track_idx
                        cell_map[(row, day_idx)] = (term_idx, day, p_idx, track_idx)
                        
                        periods_for_day = term_data.get(day, [])
                        entry = None
                        if p_idx < len(periods_for_day):
                            tracks_for_period = periods_for_day[p_idx]
                            if track_idx < len(tracks_for_period):
                                entry = tracks_for_period[track_idx]
                        
                        cell_text = "---"
                        if entry and entry[0]: # Entry is a tuple (course, teacher)
                            cell_text = f"{entry[0]}\n({entry[1]})"
                        
                        item = QTableWidgetItem(cell_text)
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        table.setItem(row, day_idx, item)

                row_cursor += num_tracks
                if p_idx < num_p - 1:
                    separator_row_index = row_cursor
                    separator_item = QTableWidgetItem()
                    separator_item.setFlags(Qt.ItemFlag.NoItemFlags)
                    separator_item.setBackground(QColor("gainsboro"))
                    table.setItem(separator_row_index, 0, separator_item)
                    table.setSpan(separator_row_index, 0, 1, table.columnCount())
                    table.setRowHeight(separator_row_index, 2)
                    row_cursor += 1
            
            table.setVerticalHeaderLabels(v_header_labels)
            
            table.resizeRowsToContents()
            table.resizeColumnsToContents()
            term_tab_widget.addTab(table, f"Term {term_idx}")

        # Add the term_tab_widget to the main_layout and return main_layout
        widget = QWidget()
        widget.setLayout(main_layout)
        return widget

    def handle_schedule_update(self, schedule_id, new_schedule_data):
        if schedule_id in self.schedules_data:
            self.schedules_data[schedule_id]['schedule'] = new_schedule_data
            self.refresh_all_schedule_views()

    def _calculate_period_times_for_display(self, params):
        if 'period_times_minutes' in params and params['period_times_minutes']:
            return [f"{format_time_from_minutes(s)}-{format_time_from_minutes(e)}"
                    for s, e in params['period_times_minutes']]
        return [f"P{i+1}" for i in range(params.get('num_periods_per_day', 1))]
