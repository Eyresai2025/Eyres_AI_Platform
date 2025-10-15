import sys
import os
import json
import shutil
import base64
from PyQt5 import QtWidgets, QtGui, QtCore, QtPrintSupport

# ==================== ANNOTATION TOOL CLASSES ====================

class ZoomableCanvas(QtWidgets.QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = None
        self.image_label = QtWidgets.QLabel()
        self.image_label.setBackgroundRole(QtGui.QPalette.Base)
        self.image_label.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self.image_label.setScaledContents(False)
        self.image_label.setAlignment(QtCore.Qt.AlignCenter)
        
        self.setBackgroundRole(QtGui.QPalette.Dark)
        self.setWidget(self.image_label)
        self.setAlignment(QtCore.Qt.AlignCenter)
        
        self.scale_factor = 1.0
        self.pixmap = None
        self.original_pixmap = None
        self.shapes = []
        self.current_shape = []
        self.drawing = False
        self.mode = 'rect'
        self.current_label = "object"
        
        # Undo/Redo functionality
        self.undo_stack = []
        self.redo_stack = []
        
        # Selection and adjustment
        self.selected_shape_index = -1
        self.selected_point_index = -1
        self.dragging = False
        self.resize_handle_size = 8
        
        # Copy/paste functionality
        self.copied_shape = None
        self.annotation_items = []
        # Zoom settings
        self.zoom_in_factor = 1.25
        self.zoom_out_factor = 1 / self.zoom_in_factor
        
        # Enable mouse tracking for better interaction
        self.setMouseTracking(True)
        self.image_label.setMouseTracking(True)

    def load_image(self, path):
        self.original_pixmap = QtGui.QPixmap(path)
        self.pixmap = self.original_pixmap
        self.image_label.setPixmap(self.pixmap)
        self.scale_factor = 1.0
        self.fit_to_window()
        self.shapes.clear()
        self.current_shape.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.selected_shape_index = -1
        self.selected_point_index = -1
        self.clear_annotation_items()
        
    def fit_to_window(self):
        if self.pixmap:
            self.image_label.adjustSize()
            factor = min(self.width() / self.pixmap.width(), 
                        self.height() / self.pixmap.height()) * 0.9
            self.scale_image(factor)
            
    def scale_image(self, factor):
        if not self.original_pixmap:
            return
            
        self.scale_factor *= factor
        new_width = int(self.original_pixmap.width() * self.scale_factor)
        new_height = int(self.original_pixmap.height() * self.scale_factor)
        
        # Scale the original pixmap to maintain quality
        self.pixmap = self.original_pixmap.scaled(
            new_width, new_height, 
            QtCore.Qt.KeepAspectRatio, 
            QtCore.Qt.SmoothTransformation
        )
        self.image_label.setPixmap(self.pixmap)
        self.image_label.resize(self.pixmap.size())
        
        self.adjust_scrollbar(self.horizontalScrollBar(), factor)
        self.adjust_scrollbar(self.verticalScrollBar(), factor)
        
    def adjust_scrollbar(self, scrollbar, factor):
        scrollbar.setValue(int(factor * scrollbar.value() + ((factor - 1) * scrollbar.pageStep()/2)))
        
    def zoom_in(self):
        self.scale_image(self.zoom_in_factor)
        
    def zoom_out(self):
        self.scale_image(self.zoom_out_factor)
        
    def normal_size(self):
        self.scale_factor = 1.0
        self.image_label.adjustSize()
        
    def get_image_coordinates(self, event_pos):
        """Convert widget coordinates to original image coordinates"""
        if not self.pixmap or not self.original_pixmap:
            return QtCore.QPoint(0, 0)
            
        # Get the position relative to the image label
        label_pos = self.image_label.mapFrom(self, event_pos)
        
        # Calculate the scale factor between displayed image and original image
        display_width = self.pixmap.width()
        display_height = self.pixmap.height()
        original_width = self.original_pixmap.width()
        original_height = self.original_pixmap.height()
        
        # Calculate the offset if the image is centered
        x_offset = (self.image_label.width() - display_width) / 2
        y_offset = (self.image_label.height() - display_height) / 2
        
        # Adjust for centering
        adj_x = label_pos.x() - x_offset
        adj_y = label_pos.y() - y_offset
        
        # Convert to original image coordinates
        if display_width > 0 and display_height > 0:
            x = int(adj_x * original_width / display_width)
            y = int(adj_y * original_height / display_height)
            
            # Clamp to image boundaries
            x = max(0, min(x, original_width - 1))
            y = max(0, min(y, original_height - 1))
            
            return QtCore.QPoint(x, y)
            
        return QtCore.QPoint(0, 0)

    # ... [Include all other ZoomableCanvas methods from your original code] ...
    # For brevity, I'm including the essential methods. You should copy ALL methods from your original ZoomableCanvas class

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self.pixmap:
            pos = self.get_image_coordinates(event.pos())
            
            if self.mode == 'rect':
                # Check if clicking on existing shape
                shape_index, point_index = self.get_shape_at_position(pos)
                if shape_index != -1:
                    self.selected_shape_index = shape_index
                    self.selected_point_index = point_index
                    self.dragging = True
                    # Save state for undo
                    self.save_state()
                else:
                    self.drawing = True
                    self.current_shape = [pos, pos]
                    self.selected_shape_index = -1
            elif self.mode == 'polygon':
                shape_index, point_index = self.get_shape_at_position(pos)
                if shape_index != -1:
                    self.selected_shape_index = shape_index
                    self.selected_point_index = point_index
                    self.dragging = True
                    self.save_state()
                else:
                    self.current_shape.append(pos)
            elif self.mode == 'select':
                shape_index, point_index = self.get_shape_at_position(pos)
                self.selected_shape_index = shape_index
                self.selected_point_index = point_index
                if shape_index != -1:
                    self.dragging = True
                    self.save_state()
                
        elif event.button() == QtCore.Qt.RightButton and self.mode == 'polygon':
            self.finish_polygon()
                
        self.update()
        
    def mouseMoveEvent(self, event):
        if self.drawing and self.mode == 'rect' and self.pixmap:
            pos = self.get_image_coordinates(event.pos())
            self.current_shape[1] = pos
        elif self.dragging and self.selected_shape_index != -1 and self.pixmap:
            pos = self.get_image_coordinates(event.pos())
            self.update_shape_position(pos)
        self.update()
            
    def mouseReleaseEvent(self, event):
        if self.drawing and self.mode == 'rect' and self.pixmap:
            self.drawing = False
            if self.current_shape and self.current_label:
                # Save state before adding new shape
                self.save_state()
                self.shapes.append(('rect', self.current_shape.copy(), self.current_label))
                # Trigger auto-save
                if hasattr(self.main_window, 'auto_save_annotations'):
                    self.main_window.auto_save_annotations()
                # AUTO-OPEN LABEL EDITOR - USE main_window INSTEAD OF parent()
                if hasattr(self.main_window, 'auto_open_label_editor'):
                    QtCore.QTimer.singleShot(100, self.main_window.auto_open_label_editor)
                else:
                    print("DEBUG: auto_open_label_editor not found in main_window")
            self.current_shape.clear()
        elif self.dragging:
            self.dragging = False
            # Trigger auto-save after moving/resizing
            if hasattr(self.main_window, 'auto_save_annotations'):
                self.main_window.auto_save_annotations()
        self.update()

    def get_shape_at_position(self, pos, threshold=10):
        """Check if position is near any shape or control point"""
        for i, (shape_type, points, label) in enumerate(self.shapes):
            if shape_type == 'rect':
                rect = QtCore.QRect(points[0], points[1]).normalized()
                # Check if near edges or corners
                if rect.contains(pos):
                    return i, -1  # -1 means moving entire shape
                
                # Check corners for resizing
                corners = [
                    rect.topLeft(), rect.topRight(), 
                    rect.bottomLeft(), rect.bottomRight()
                ]
                for j, corner in enumerate(corners):
                    if (pos - corner).manhattanLength() < threshold:
                        return i, j
                        
            elif shape_type == 'polygon':
                # Check if near any point
                for j, point in enumerate(points):
                    if (pos - point).manhattanLength() < threshold:
                        return i, j
                # Check if inside polygon
                poly = QtGui.QPolygon(points)
                if poly.containsPoint(pos, QtCore.Qt.OddEvenFill):
                    return i, -1
                    
        return -1, -1

    def update_shape_position(self, pos):
        """Update shape position based on drag operation"""
        if self.selected_shape_index < 0 or self.selected_shape_index >= len(self.shapes):
            return
            
        shape_type, points, label = self.shapes[self.selected_shape_index]
        
        if shape_type == 'rect':
            rect = QtCore.QRect(points[0], points[1]).normalized()
            
            if self.selected_point_index == -1:  # Moving entire rectangle
                delta = pos - rect.center()
                new_tl = points[0] + delta
                new_br = points[1] + delta
                self.shapes[self.selected_shape_index] = (shape_type, [new_tl, new_br], label)
            else:  # Resizing from corner
                corners = [rect.topLeft(), rect.topRight(), rect.bottomLeft(), rect.bottomRight()]
                corners[self.selected_point_index] = pos
                
                # Reconstruct rectangle from updated corners
                new_tl = QtCore.QPoint(min(corners[0].x(), corners[2].x()), min(corners[0].y(), corners[1].y()))
                new_br = QtCore.QPoint(max(corners[1].x(), corners[3].x()), max(corners[2].y(), corners[3].y()))
                self.shapes[self.selected_shape_index] = (shape_type, [new_tl, new_br], label)
                
        elif shape_type == 'polygon':
            if self.selected_point_index >= 0 and self.selected_point_index < len(points):
                # Move specific point
                new_points = points.copy()
                new_points[self.selected_point_index] = pos
                self.shapes[self.selected_shape_index] = (shape_type, new_points, label)
            elif self.selected_point_index == -1:  # Moving entire polygon
                # Calculate center and move all points
                center = self.get_polygon_center(points)
                delta = pos - center
                new_points = [p + delta for p in points]
                self.shapes[self.selected_shape_index] = (shape_type, new_points, label)

    def get_polygon_center(self, points):
        """Calculate center point of polygon"""
        if not points:
            return QtCore.QPoint(0, 0)
        x_sum = sum(p.x() for p in points)
        y_sum = sum(p.y() for p in points)
        return QtCore.QPoint(x_sum // len(points), y_sum // len(points))

    def wheelEvent(self, event):
        """Handle zoom with Ctrl+Mouse Wheel"""
        if event.modifiers() & QtCore.Qt.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Delete and self.selected_shape_index != -1:
            self.delete_selected_shape()
        elif event.key() == QtCore.Qt.Key_Escape:
            self.cancel_operation()
        elif event.modifiers() & QtCore.Qt.ControlModifier:
            if event.key() == QtCore.Qt.Key_Z:
                self.undo()
            elif event.key() == QtCore.Qt.Key_Y:
                self.redo()
            elif event.key() == QtCore.Qt.Key_C:
                self.copy_selected_shape()
            elif event.key() == QtCore.Qt.Key_V:
                self.paste_shape()
        else:
            super().keyPressEvent(event)

    def delete_selected_shape(self):
        if self.selected_shape_index != -1:
            self.save_state()
            del self.shapes[self.selected_shape_index]
            self.selected_shape_index = -1
            # Trigger auto-save - USE main_window
            if hasattr(self.main_window, 'auto_save_annotations'):
                self.main_window.auto_save_annotations()
            self.update()

    def copy_selected_shape(self):
        if self.selected_shape_index != -1:
            shape_type, points, label = self.shapes[self.selected_shape_index]
            self.copied_shape = (shape_type, [QtCore.QPoint(p) for p in points], label)

    def paste_shape(self):
        if self.copied_shape and self.pixmap:
            self.save_state()
            shape_type, points, label = self.copied_shape
            # Offset the copied shape slightly
            offset = QtCore.QPoint(20, 20)
            new_points = [p + offset for p in points]
            self.shapes.append((shape_type, new_points, label))
            self.selected_shape_index = len(self.shapes) - 1
            # Trigger auto-save
            if hasattr(self.main_window, 'auto_save_annotations'):
                self.main_window.auto_save_annotations()
            self.update()

    def edit_selected_label(self, new_label):
        if self.selected_shape_index != -1:
            self.save_state()
            shape_type, points, old_label = self.shapes[self.selected_shape_index]
            self.shapes[self.selected_shape_index] = (shape_type, points, new_label)
            # Trigger auto-save
            if hasattr(self.main_window, 'auto_save_annotations'):
                self.main_window.auto_save_annotations()
            self.update()

    def cancel_operation(self):
        if self.mode == 'polygon':
            self.current_shape.clear()
        self.selected_shape_index = -1
        self.drawing = False
        self.dragging = False
        self.update()

    def save_state(self):
        """Save current state to undo stack"""
        state = {
            'shapes': [(shape_type, [QtCore.QPoint(p) for p in points], label) 
                      for shape_type, points, label in self.shapes],
            'current_shape': [QtCore.QPoint(p) for p in self.current_shape],
            'selected_index': self.selected_shape_index
        }
        self.undo_stack.append(state)
        self.redo_stack.clear()  # Clear redo stack when new action is performed
        
        # Limit undo stack size
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

    def undo(self):
        """Undo last action"""
        if self.undo_stack:
            # Save current state to redo stack
            current_state = {
                'shapes': [(shape_type, [QtCore.QPoint(p) for p in points], label) 
                          for shape_type, points, label in self.shapes],
                'current_shape': [QtCore.QPoint(p) for p in self.current_shape],
                'selected_index': self.selected_shape_index
            }
            self.redo_stack.append(current_state)
            
            # Restore previous state
            state = self.undo_stack.pop()
            self.shapes = [(shape_type, points, label) for shape_type, points, label in state['shapes']]
            self.current_shape = state['current_shape']
            self.selected_shape_index = state['selected_index']
            self.update()

    def redo(self):
        """Redo last undone action"""
        if self.redo_stack:
            # Save current state to undo stack
            current_state = {
                'shapes': [(shape_type, [QtCore.QPoint(p) for p in points], label) 
                          for shape_type, points, label in self.shapes],
                'current_shape': [QtCore.QPoint(p) for p in self.current_shape],
                'selected_index': self.selected_shape_index
            }
            self.undo_stack.append(current_state)
            
            # Restore redone state
            state = self.redo_stack.pop()
            self.shapes = [(shape_type, points, label) for shape_type, points, label in state['shapes']]
            self.current_shape = state['current_shape']
            self.selected_shape_index = state['selected_index']
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.pixmap or not self.original_pixmap:
            return
            
        # Create a new pixmap to draw on (use original for accurate coordinates)
        temp_pixmap = self.original_pixmap.copy()
        painter = QtGui.QPainter(temp_pixmap)
        
        if not painter.isActive():
            return
            
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        # Draw existing shapes
        for i, (shape_type, points, label) in enumerate(self.shapes):
            color = self.get_color_for_label(label)
            pen = QtGui.QPen(color, 3)
            painter.setPen(pen)
            
            if shape_type == 'rect':
                rect = QtCore.QRect(points[0], points[1])
                painter.drawRect(rect)
                
                # Draw selection handles if selected
                if i == self.selected_shape_index:
                    self.draw_selection_handles(painter, rect)
                
                # Draw label
                painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 2))
                painter.drawText(points[0].x() + 5, points[0].y() - 5, label)
                
            elif shape_type == 'polygon':
                poly = QtGui.QPolygon(points)
                painter.drawPolygon(poly)
                
                # Draw selection handles if selected
                if i == self.selected_shape_index:
                    for point in points:
                        painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 0)))
                        painter.drawEllipse(point, 4, 4)
                
                if points:
                    painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 2))
                    painter.drawText(points[0].x() + 5, points[0].y() - 5, label)
                    
        # Draw current shape
        if self.current_shape:
            color = QtGui.QColor(255, 0, 0)  # Red for current shape
            pen = QtGui.QPen(color, 2, QtCore.Qt.DashLine)
            painter.setPen(pen)
            
            if self.mode == 'rect' and len(self.current_shape) == 2:
                rect = QtCore.QRect(self.current_shape[0], self.current_shape[1])
                painter.drawRect(rect)
            elif self.mode == 'polygon' and self.current_shape:
                poly = QtGui.QPolygon(self.current_shape)
                painter.drawPolyline(poly)
                # Draw points
                for point in self.current_shape:
                    painter.drawEllipse(point, 3, 3)
        
        painter.end()
        
        # Scale the annotated pixmap to current display size
        scaled_pixmap = temp_pixmap.scaled(
            self.pixmap.size(),
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled_pixmap)

    def draw_selection_handles(self, painter, rect):
        """Draw selection handles around rectangle"""
        painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 0)))
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0), 1))
        
        handles = [
            rect.topLeft(), rect.topRight(), 
            rect.bottomLeft(), rect.bottomRight(),
            QtCore.QPoint(rect.center().x(), rect.top()),
            QtCore.QPoint(rect.center().x(), rect.bottom()),
            QtCore.QPoint(rect.left(), rect.center().y()),
            QtCore.QPoint(rect.right(), rect.center().y())
        ]
        
        for handle in handles:
            painter.drawRect(handle.x() - 4, handle.y() - 4, 8, 8)

    def get_color_for_label(self, label):
        # Generate consistent color based on label
        import hashlib
        hash_obj = hashlib.md5(label.encode())
        hash_int = int(hash_obj.hexdigest()[:8], 16)
        r = (hash_int >> 16) & 255
        g = (hash_int >> 8) & 255
        b = hash_int & 255
        return QtGui.QColor(r, g, b)

    def set_mode(self, mode):
        self.mode = mode
        self.current_shape.clear()
        self.selected_shape_index = -1
        self.update()

    def set_label(self, label):
        self.current_label = label

    def finish_polygon(self):
        if len(self.current_shape) > 2 and self.current_label:
            self.save_state()
            self.shapes.append(('polygon', self.current_shape.copy(), self.current_label))
            self.current_shape.clear()
            # Trigger auto-save
            if hasattr(self.main_window, 'auto_save_annotations'):
                self.main_window.auto_save_annotations()
            # AUTO-OPEN LABEL EDITOR FOR POLYGON - USE main_window
            if hasattr(self.main_window, 'auto_open_label_editor'):
                QtCore.QTimer.singleShot(100, self.main_window.auto_open_label_editor)
            self.update()

    def get_annotations(self):
        annotations = []
        for shape_type, points, label in self.shapes:
            if shape_type == 'rect':
                x1, y1 = points[0].x(), points[0].y()
                x2, y2 = points[1].x(), points[1].y()
                annotations.append({
                    'label': label,
                    'shape': 'rectangle',
                    'points': [[x1, y1], [x2, y2]],
                    'bbox': [min(x1, x2), min(y1, y2), abs(x2-x1), abs(y2-y1)]
                })
            elif shape_type == 'polygon':
                pts = [[p.x(), p.y()] for p in points]
                x_coords = [p[0] for p in pts]
                y_coords = [p[1] for p in pts]
                annotations.append({
                    'label': label,
                    'shape': 'polygon',
                    'points': pts,
                    'bbox': [min(x_coords), min(y_coords), 
                            max(x_coords)-min(x_coords), max(y_coords)-min(y_coords)]
                })
        return annotations

    def clear_annotations(self):
        self.save_state()
        self.shapes.clear()
        self.selected_shape_index = -1
        self.update()

    def clear_annotation_items(self):
        """Clear all annotation graphics items"""
        self.annotation_items.clear()

    def add_annotation_rect(self, rect, label):
        """Add rectangle annotation to display"""
        print(f"Adding rectangle: {rect}, label: {label}")

    def add_annotation_polygon(self, polygon, label):
        """Add polygon annotation to display"""
        print(f"Adding polygon: {polygon.size()} points, label: {label}")

class ThumbnailList(QtWidgets.QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QtWidgets.QListWidget.IconMode)
        self.setIconSize(QtCore.QSize(100, 100))
        self.setResizeMode(QtWidgets.QListWidget.Adjust)
        self.setFlow(QtWidgets.QListWidget.LeftToRight)
        self.setWrapping(True)
        self.setSpacing(5)
        
    def load_images(self, image_paths):
        self.clear()
        for path in image_paths:
            item = QtWidgets.QListWidgetItem()
            pixmap = QtGui.QPixmap(path)
            if not pixmap.isNull():
                # Scale pixmap to thumbnail size while maintaining aspect ratio
                scaled_pixmap = pixmap.scaled(
                    self.iconSize().width(), 
                    self.iconSize().height(), 
                    QtCore.Qt.KeepAspectRatio, 
                    QtCore.Qt.SmoothTransformation
                )
                icon = QtGui.QIcon(scaled_pixmap)
                item.setIcon(icon)
                item.setText(os.path.basename(path))
                item.setData(QtCore.Qt.UserRole, path)
                self.addItem(item)

class LabelSelectionDialog(QtWidgets.QDialog):
    def __init__(self, existing_labels, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Label")
        self.setModal(True)
        self.selected_label = None
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # Title
        title = QtWidgets.QLabel("Select or Enter Label")
        title.setStyleSheet("font-size: 14px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        # Existing labels list
        if existing_labels:
            list_label = QtWidgets.QLabel("Existing Labels:")
            layout.addWidget(list_label)
            
            self.list_widget = QtWidgets.QListWidget()
            self.list_widget.addItems(existing_labels)
            self.list_widget.itemDoubleClicked.connect(self.accept_selection)
            layout.addWidget(self.list_widget)
        
        # New label input
        new_label_layout = QtWidgets.QHBoxLayout()
        new_label_layout.addWidget(QtWidgets.QLabel("New Label:"))
        self.label_input = QtWidgets.QLineEdit()
        self.label_input.returnPressed.connect(self.accept_custom)
        new_label_layout.addWidget(self.label_input)
        layout.addLayout(new_label_layout)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        btn_ok = QtWidgets.QPushButton("OK")
        btn_ok.clicked.connect(self.accept_custom)
        
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        
        button_layout.addWidget(btn_ok)
        button_layout.addWidget(btn_cancel)
        layout.addLayout(button_layout)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #2D2D3C;
                color: white;
            }
            QListWidget {
                background-color: #454558;
                color: white;
            }
            QLineEdit {
                background-color: #454558;
                color: white;
            }
        """)
        
    def accept_selection(self, item):
        self.selected_label = item.text()
        self.accept()
        
    def accept_custom(self):
        if self.label_input.text().strip():
            self.selected_label = self.label_input.text().strip()
            self.accept()
        
    def get_selected_label(self):
        return self.selected_label

# ==================== EMBEDDABLE ANNOTATION TOOL ====================

class AnnotationTool(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Set window size based on parent or default
        if parent:
            self.resize(parent.width() * 0.9, parent.height() * 0.9)
        else:
            self.resize(1200, 800)
            
        self.folder = ""
        self.images = []
        self.current_index = -1
        self.current_image = None
        self.annotations = {}
        self.annotation_folder = ""
        
        # New attributes for auto-save and verification
        self.auto_save_enabled = True
        self.pending_saves = set()
        self.final_save_mode = False
        self.existing_labels = set()  # Track all labels used in the session
        
        self.init_ui()
        
    def init_ui(self):
        # Create main layout (no central widget for QWidget)
        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Left panel for thumbnails and controls
        left_panel = QtWidgets.QWidget()
        left_panel.setMaximumWidth(320)
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        
        
        # Help button with icon and text
        help_btn = QtWidgets.QPushButton()
        help_icon_path = r"E:\Office\Desktop\My files\project files\Apollo_Streamlit\question.png"

        try:
            if os.path.exists(help_icon_path):
                help_icon = QtGui.QIcon(help_icon_path)
                if not help_icon.isNull():
                    help_btn.setIcon(help_icon)
                    help_btn.setText(" Help / Instructions")
                else:
                    raise Exception("Invalid icon file")
            else:
                raise Exception("Help icon file not found")
        except Exception as e:
            print(f"Help icon loading error: {e}")
            # Fallback to question mark if icon fails
            help_btn.setText("Help / Instructions")
        help_btn.setToolTip("View keyboard shortcuts and usage instructions") 
        help_btn.clicked.connect(self.show_help)
        left_layout.addWidget(help_btn)
        
        # Folder controls
        folder_group = QtWidgets.QGroupBox("Folder Operations")
        folder_layout = QtWidgets.QVBoxLayout(folder_group)
        
        self.browse_btn = QtWidgets.QPushButton()
        folder_icon_path = r"E:\Office\Desktop\My files\project files\Apollo_Streamlit\folder.png"

        try:
            if os.path.exists(folder_icon_path):
                folder_icon = QtGui.QIcon(folder_icon_path)
                if not folder_icon.isNull():
                    self.browse_btn.setIcon(folder_icon)
                    self.browse_btn.setText(" Open Image Folder")
                else:
                    raise Exception("Invalid icon file")
            else:
                raise Exception("Folder icon file not found")
        except Exception as e:
            print(f"Folder icon loading error: {e}")
            # Fallback to folder symbol if icon fails
            self.browse_btn.setText("📁 Open Image Folder")
        self.browse_btn.setToolTip("Load only image files from a folder (without annotations)")
        self.browse_btn.clicked.connect(self.browse_folder)
        folder_layout.addWidget(self.browse_btn)
        
        self.browse_with_annotations_btn = QtWidgets.QPushButton()
        folder_annotations_icon_path = r"E:\Office\Desktop\My files\project files\Apollo_Streamlit\folder.png"

        try:
            if os.path.exists(folder_annotations_icon_path):
                folder_annotations_icon = QtGui.QIcon(folder_annotations_icon_path)
                if not folder_annotations_icon.isNull():
                    self.browse_with_annotations_btn.setIcon(folder_annotations_icon)
                    self.browse_with_annotations_btn.setText(" Open Folder with Images & Annotations")
                else:
                    raise Exception("Invalid icon file")
            else:
                raise Exception("Folder with annotations icon file not found")
        except Exception as e:
            print(f"Folder with annotations icon loading error: {e}")
            # Fallback to folder symbol if icon fails
            self.browse_with_annotations_btn.setText("📂 Open Folder with Images & Annotations")
        self.browse_with_annotations_btn.setToolTip("Load both images and their annotation files from a folder") 
        self.browse_with_annotations_btn.clicked.connect(self.load_folder_with_annotations)
        folder_layout.addWidget(self.browse_with_annotations_btn)
        
        self.annotated_count_label = QtWidgets.QLabel("Annotated: 0/0")
        folder_layout.addWidget(self.annotated_count_label)
        
        left_layout.addWidget(folder_group)
        
        # Annotation controls
        annotate_group = QtWidgets.QGroupBox("Annotation Tools")
        annotate_layout = QtWidgets.QVBoxLayout(annotate_group)
        
        # Mode selection
        mode_layout = QtWidgets.QHBoxLayout()
        mode_layout.addWidget(QtWidgets.QLabel("Tool:"))
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems(["Rectangle", "Polygon", "Select"])
        self.mode_combo.currentTextChanged.connect(self.change_mode)
        mode_layout.addWidget(self.mode_combo)
        annotate_layout.addLayout(mode_layout)
        
        # Label management
        label_layout = QtWidgets.QHBoxLayout()
        label_layout.addWidget(QtWidgets.QLabel("Label:"))
        self.label_input = QtWidgets.QLineEdit()
        self.label_input.setPlaceholderText("Enter object label")
        self.label_input.textChanged.connect(self.update_current_label)
        label_layout.addWidget(self.label_input)
        
        annotate_layout.addLayout(label_layout)
        
        # Annotation actions in a grid layout
        action_grid = QtWidgets.QGridLayout()
        
        self.finish_polygon_btn = QtWidgets.QPushButton("Finish Polygon")
        finish_polygon_icon_path = r"E:\Office\Desktop\My files\project files\Apollo_Streamlit\Finish.png"

        try:
            if os.path.exists(finish_polygon_icon_path):
                finish_polygon_icon = QtGui.QIcon(finish_polygon_icon_path)
                if not finish_polygon_icon.isNull():
                    self.finish_polygon_btn.setIcon(finish_polygon_icon)
                else:
                    raise Exception("Invalid icon file")
            else:
                raise Exception("Finish polygon icon file not found")
        except Exception as e:
            print(f"Finish polygon icon loading error: {e}")
            self.finish_polygon_btn.setText("Finish Polygon")
        self.finish_polygon_btn.setToolTip("Complete the current polygon (Right-click also works)")
        self.finish_polygon_btn.clicked.connect(self.finish_polygon)
        action_grid.addWidget(self.finish_polygon_btn, 0, 0)
        
        self.clear_btn = QtWidgets.QPushButton("Clear Annotations")
        clear_icon_path = r"E:\Office\Desktop\My files\project files\Apollo_Streamlit\clear.png"
        try:
            if os.path.exists(clear_icon_path):
                clear_icon = QtGui.QIcon(clear_icon_path)
                if not clear_icon.isNull():
                    self.clear_btn.setIcon(clear_icon)
                else:
                    raise Exception("Invalid icon file")
            else:
                raise Exception("Clear icon file not found")
        except Exception as e:
            print(f"Clear icon loading error: {e}")
            self.clear_btn.setText("Clear Annotations")
        self.clear_btn.setToolTip("Remove all annotations from the current image")
        self.clear_btn.clicked.connect(self.clear_annotations)
        action_grid.addWidget(self.clear_btn, 0, 1)
        
        self.edit_label_btn = QtWidgets.QPushButton()
        edit_label_icon_path = r"E:\Office\Desktop\My files\project files\Apollo_Streamlit\edit-image.png"

        try:
            if os.path.exists(edit_label_icon_path):
                edit_label_icon = QtGui.QIcon(edit_label_icon_path)
                if not edit_label_icon.isNull():
                    self.edit_label_btn.setIcon(edit_label_icon)
                    self.edit_label_btn.setText(" Edit Label")
                else:
                    raise Exception("Invalid icon file")
            else:
                raise Exception("Edit label icon file not found")
        except Exception as e:
            print(f"Edit label icon loading error: {e}")
            self.edit_label_btn.setText("✏️ Edit Label")

        self.edit_label_btn.clicked.connect(self.edit_selected_label)
        self.edit_label_btn.setToolTip("Edit selected annotation label (E)")
        action_grid.addWidget(self.edit_label_btn, 1, 0)
        
        self.delete_btn = QtWidgets.QPushButton()
        delete_icon_path = r"E:\Office\Desktop\My files\project files\Apollo_Streamlit\delete.png"

        try:
            if os.path.exists(delete_icon_path):
                delete_icon = QtGui.QIcon(delete_icon_path)
                if not delete_icon.isNull():
                    self.delete_btn.setIcon(delete_icon)
                    self.delete_btn.setText(" Delete Selected")
                else:
                    raise Exception("Invalid icon file")
            else:
                raise Exception("Delete icon file not found")
        except Exception as e:
            print(f"Delete icon loading error: {e}")
            self.delete_btn.setText("🗑️ Delete Selected")

        self.delete_btn.setToolTip("Delete selected annotation (Delete or Ctrl+D)")
        self.delete_btn.clicked.connect(self.delete_selected)
        action_grid.addWidget(self.delete_btn, 1, 1)
        
        self.copy_btn = QtWidgets.QPushButton()
        copy_icon_path = r"E:\Office\Desktop\My files\project files\Apollo_Streamlit\copy.png"

        try:
            if os.path.exists(copy_icon_path):
                copy_icon = QtGui.QIcon(copy_icon_path)
                if not copy_icon.isNull():
                    self.copy_btn.setIcon(copy_icon)
                    self.copy_btn.setText(" Copy")
                else:
                    raise Exception("Invalid icon file")
            else:
                raise Exception("Copy icon file not found")
        except Exception as e:
            print(f"Copy icon loading error: {e}")
            self.copy_btn.setText("📋 Copy")

        self.copy_btn.setToolTip("Copy selected annotation (Ctrl+C)")
        self.copy_btn.clicked.connect(self.copy_selected)
        action_grid.addWidget(self.copy_btn, 2, 0)

        self.paste_btn = QtWidgets.QPushButton()
        paste_icon_path = r"E:\Office\Desktop\My files\project files\Apollo_Streamlit\paste.png"

        try:
            if os.path.exists(paste_icon_path):
                paste_icon = QtGui.QIcon(paste_icon_path)
                if not paste_icon.isNull():
                    self.paste_btn.setIcon(paste_icon)
                    self.paste_btn.setText(" Paste")
                else:
                    raise Exception("Invalid icon file")
            else:
                raise Exception("Paste icon file not found")
        except Exception as e:
            print(f"Paste icon loading error: {e}")
            self.paste_btn.setText("📎 Paste")

        self.paste_btn.setToolTip("Paste copied annotation (Ctrl+V)")
        self.paste_btn.clicked.connect(self.paste_shape)
        action_grid.addWidget(self.paste_btn, 2, 1)
        
        annotate_layout.addLayout(action_grid)
        
        left_layout.addWidget(annotate_group)
        
        # Zoom controls
        zoom_group = QtWidgets.QGroupBox("Zoom Tools")
        zoom_layout = QtWidgets.QHBoxLayout(zoom_group)
        
        self.zoom_in_btn = QtWidgets.QPushButton("Zoom In")
        zoom_in_icon_path = r"E:\Office\Desktop\My files\project files\Apollo_Streamlit\Zoomin.png"

        try:
            if os.path.exists(zoom_in_icon_path):
                zoom_in_icon = QtGui.QIcon(zoom_in_icon_path)
                if not zoom_in_icon.isNull():
                    self.zoom_in_btn.setIcon(zoom_in_icon)
                else:
                    raise Exception("Invalid icon file")
            else:
                raise Exception("Zoom in icon file not found")
        except Exception as e:
            print(f"Zoom in icon loading error: {e}")
            self.zoom_in_btn.setText("Zoom In")
        self.zoom_in_btn.setToolTip("Zoom in on the image (Ctrl+Mouse Wheel Up)")
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        zoom_layout.addWidget(self.zoom_in_btn)
        
        self.zoom_out_btn = QtWidgets.QPushButton("Zoom Out")
        zoom_out_icon_path = r"E:\Office\Desktop\My files\project files\Apollo_Streamlit\Zoomout.png"

        try:
            if os.path.exists(zoom_out_icon_path):
                zoom_out_icon = QtGui.QIcon(zoom_out_icon_path)
                if not zoom_out_icon.isNull():
                    self.zoom_out_btn.setIcon(zoom_out_icon)
                else:
                    raise Exception("Invalid icon file")
            else:
                raise Exception("Zoom out icon file not found")
        except Exception as e:
            print(f"Zoom out icon loading error: {e}")
            self.zoom_out_btn.setText("Zoom Out")
        self.zoom_out_btn.setToolTip("Zoom out on the image (Ctrl+Mouse Wheel Down)")
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        zoom_layout.addWidget(self.zoom_out_btn)
        
        self.fit_btn = QtWidgets.QPushButton("Window")
        fit_icon_path = r"E:\Office\Desktop\My files\project files\Apollo_Streamlit\window.png"

        try:
            if os.path.exists(fit_icon_path):
                fit_icon = QtGui.QIcon(fit_icon_path)
                if not fit_icon.isNull():
                    self.fit_btn.setIcon(fit_icon)
                else:
                    raise Exception("Invalid icon file")
            else:
                raise Exception("Fit to window icon file not found")
        except Exception as e:
            print(f"Fit to window icon loading error: {e}")
            self.fit_btn.setText("Window")

        self.fit_btn.clicked.connect(self.fit_to_window)
        self.fit_btn.setToolTip("Fit image to window size")
        zoom_layout.addWidget(self.fit_btn)
        
        left_layout.addWidget(zoom_group)
        
        # Navigation controls
        nav_group = QtWidgets.QGroupBox("Navigation")
        nav_layout = QtWidgets.QHBoxLayout(nav_group)

        self.prev_btn = QtWidgets.QPushButton()
        prev_icon_path = r"E:\Office\Desktop\My files\project files\Apollo_Streamlit\back.png"
        try:
            if os.path.exists(prev_icon_path):
                prev_icon = QtGui.QIcon(prev_icon_path)
                if not prev_icon.isNull():
                    self.prev_btn.setIcon(prev_icon)
                    self.prev_btn.setText(" Previous")
                else:
                    raise Exception("Invalid icon file")
            else:
                raise Exception("Previous icon file not found")
        except Exception as e:
            print(f"Previous icon loading error: {e}")
            self.prev_btn.setText("⬅ Previous")
        self.prev_btn.setToolTip("Go to previous image (A or Left Arrow)")
        self.prev_btn.clicked.connect(self.prev_image)
        nav_layout.addWidget(self.prev_btn)

        self.next_btn = QtWidgets.QPushButton("Next")
        next_icon_path = r"E:\Office\Desktop\My files\project files\Apollo_Streamlit\image.png" 

        try:
            if os.path.exists(next_icon_path):
                next_icon = QtGui.QIcon(next_icon_path)
                if not next_icon.isNull():
                    self.next_btn.setIcon(next_icon)
                else:
                    raise Exception("Invalid icon file")
            else:
                raise Exception("Next icon file not found")
        except Exception as e:
            print(f"Next icon loading error: {e}")
            self.next_btn.setText("Next ➡")
        self.next_btn.setToolTip("Go to next image (D or Right Arrow)")
        self.next_btn.clicked.connect(self.next_image)
        nav_layout.addWidget(self.next_btn)
        
        left_layout.addWidget(nav_group)
        
        # Save controls
        save_group = QtWidgets.QGroupBox("Save Operations")
        save_layout = QtWidgets.QVBoxLayout(save_group)

        self.save_current_btn = QtWidgets.QPushButton("Save Current")
        save_icon_path = r"E:\Office\Desktop\My files\project files\Apollo_Streamlit\save.png"

        try:
            if os.path.exists(save_icon_path):
                save_icon = QtGui.QIcon(save_icon_path)
                if not save_icon.isNull():
                    self.save_current_btn.setIcon(save_icon)
                else:
                    raise Exception("Invalid icon file")
            else:
                raise Exception("Save icon file not found")
        except Exception as e:
            print(f"Save icon loading error: {e}")
            self.save_current_btn.setText("💾 Save Current")
        self.save_current_btn.setToolTip("Save annotations for current image only")
        self.save_current_btn.clicked.connect(self.save_current)
        save_layout.addWidget(self.save_current_btn)

        self.save_all_btn = QtWidgets.QPushButton("Final Save & Verify")
        save_icon_path = r"E:\Office\Desktop\My files\project files\Apollo_Streamlit\save.png" 

        try:
            if os.path.exists(save_icon_path):
                save_icon = QtGui.QIcon(save_icon_path)
                if not save_icon.isNull():
                    self.save_all_btn.setIcon(save_icon)
                else:
                    raise Exception("Invalid icon file")
            else:
                raise Exception("Save icon file not found")
        except Exception as e:
            print(f"Save icon loading error: {e}")
            self.save_all_btn.setText("✅ Final Save & Verify")
        self.save_all_btn.setToolTip("Review all annotations before final export to new folder")
        self.save_all_btn.clicked.connect(self.save_all)
        save_layout.addWidget(self.save_all_btn)

        self.overwrite_btn = QtWidgets.QPushButton()
        overwrite_icon_path = r"E:\Office\Desktop\My files\project files\Apollo_Streamlit\overwrite.png"

        try:
            if os.path.exists(overwrite_icon_path):
                overwrite_icon = QtGui.QIcon(overwrite_icon_path)
                if not overwrite_icon.isNull():
                    self.overwrite_btn.setIcon(overwrite_icon)
                    self.overwrite_btn.setText(" Overwrite Existing Files")
                else:
                    raise Exception("Invalid icon file")
            else:
                raise Exception("Overwrite icon file not found")
        except Exception as e:
            print(f"Overwrite icon loading error: {e}")
            self.overwrite_btn.setText("🔄 Overwrite Existing Files")

        self.overwrite_btn.clicked.connect(self.save_and_overwrite)
        self.overwrite_btn.setToolTip("Overwrite existing annotation files in current folder")
        save_layout.addWidget(self.overwrite_btn)

        left_layout.addWidget(save_group)
        
        left_layout.addStretch()
        
        # Right panel for image and thumbnails
        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        
        # Image canvas
        self.canvas = ZoomableCanvas()
        self.canvas.main_window = self 
        right_layout.addWidget(self.canvas, 4)
        
        # Thumbnail list
        self.thumbnail_list = ThumbnailList()
        self.thumbnail_list.itemClicked.connect(self.thumbnail_clicked)
        right_layout.addWidget(self.thumbnail_list, 1)
        
        # Add panels to main layout
        main_layout.addWidget(left_panel, 1)
        main_layout.addWidget(right_panel, 3)
        
        # Apply dark theme
        self.apply_dark_theme()
        
        # Set up keyboard shortcuts
        self.setup_shortcuts()
    
    def ask_save_format(self):
        """Ask user to choose save format"""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Select Save Format")
        dialog.setModal(True)
        dialog.resize(300, 150)
        
        layout = QtWidgets.QVBoxLayout(dialog)
        
        title = QtWidgets.QLabel("Choose annotation format:")
        title.setStyleSheet("font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        # Format selection
        format_group = QtWidgets.QGroupBox("Format")
        format_layout = QtWidgets.QVBoxLayout(format_group)
        
        json_radio = QtWidgets.QRadioButton("JSON (LabelMe format)")
        xml_radio = QtWidgets.QRadioButton("XML (Pascal VOC format)")
        json_radio.setChecked(True)  # Default to JSON
        
        format_layout.addWidget(json_radio)
        format_layout.addWidget(xml_radio)
        layout.addWidget(format_group)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        btn_ok = QtWidgets.QPushButton("OK")
        btn_cancel = QtWidgets.QPushButton("Cancel")
        
        button_layout.addWidget(btn_ok)
        button_layout.addWidget(btn_cancel)
        layout.addLayout(button_layout)
        
        # Store selected format
        selected_format = "json"
        
        def on_json_toggled(checked):
            nonlocal selected_format
            if checked:
                selected_format = "json"
        
        def on_xml_toggled(checked):
            nonlocal selected_format
            if checked:
                selected_format = "xml"
        
        json_radio.toggled.connect(on_json_toggled)
        xml_radio.toggled.connect(on_xml_toggled)
        
        btn_ok.clicked.connect(dialog.accept)
        btn_cancel.clicked.connect(dialog.reject)
        
        result = dialog.exec_()
        
        if result == QtWidgets.QDialog.Accepted:
            return selected_format
        else:
            return None

    def convert_annotations_to_xml_format(self, img_path, annotations):
        """Convert annotations to Pascal VOC XML format"""
        if not self.canvas.original_pixmap:
            return None
        
        # Get image dimensions
        width = self.canvas.original_pixmap.width()
        height = self.canvas.original_pixmap.height()
        depth = 3  # Assuming RGB images
        
        # Get folder and filename
        folder_name = os.path.basename(os.path.dirname(img_path))
        file_name = os.path.basename(img_path)
        full_path = os.path.abspath(img_path)
        
        # Create XML structure
        import xml.etree.ElementTree as ET
        from xml.dom import minidom
        
        # Create root element
        annotation = ET.Element("annotation")
        
        # Folder
        folder_elem = ET.SubElement(annotation, "folder")
        folder_elem.text = folder_name
        
        # Filename
        filename_elem = ET.SubElement(annotation, "filename")
        filename_elem.text = file_name
        
        # Path
        path_elem = ET.SubElement(annotation, "path")
        path_elem.text = full_path
        
        # Source
        source_elem = ET.SubElement(annotation, "source")
        database_elem = ET.SubElement(source_elem, "database")
        database_elem.text = "Unknown"
        
        # Size
        size_elem = ET.SubElement(annotation, "size")
        width_elem = ET.SubElement(size_elem, "width")
        width_elem.text = str(width)
        height_elem = ET.SubElement(size_elem, "height")
        height_elem.text = str(height)
        depth_elem = ET.SubElement(size_elem, "depth")
        depth_elem.text = str(depth)
        
        # Segmented
        segmented_elem = ET.SubElement(annotation, "segmented")
        segmented_elem.text = "0"
        
        # Objects
        for ann in annotations:
            if ann['shape'] == 'rectangle':
                points = ann['points']
                if len(points) >= 2:
                    # Extract coordinates
                    x_coords = [point[0] for point in points]
                    y_coords = [point[1] for point in points]
                    
                    xmin = int(min(x_coords))
                    ymin = int(min(y_coords))
                    xmax = int(max(x_coords))
                    ymax = int(max(y_coords))
                    
                    # Create object element
                    object_elem = ET.SubElement(annotation, "object")
                    
                    # Name
                    name_elem = ET.SubElement(object_elem, "name")
                    name_elem.text = ann['label']
                    
                    # Pose
                    pose_elem = ET.SubElement(object_elem, "pose")
                    pose_elem.text = "Unspecified"
                    
                    # Truncated
                    truncated_elem = ET.SubElement(object_elem, "truncated")
                    truncated_elem.text = "0"
                    
                    # Difficult
                    difficult_elem = ET.SubElement(object_elem, "difficult")
                    difficult_elem.text = "0"
                    
                    # Bounding box
                    bndbox_elem = ET.SubElement(object_elem, "bndbox")
                    xmin_elem = ET.SubElement(bndbox_elem, "xmin")
                    xmin_elem.text = str(xmin)
                    ymin_elem = ET.SubElement(bndbox_elem, "ymin")
                    ymin_elem.text = str(ymin)
                    xmax_elem = ET.SubElement(bndbox_elem, "xmax")
                    xmax_elem.text = str(xmax)
                    ymax_elem = ET.SubElement(bndbox_elem, "ymax")
                    ymax_elem.text = str(ymax)
        
        # Convert to pretty XML string
        rough_string = ET.tostring(annotation, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="\t")
        
        return pretty_xml
    
    def save_annotations_as_xml(self, img_path, output_folder, overwrite=False):
        """Save annotations as XML file in Pascal VOC format"""
        if img_path not in self.annotations or not self.annotations[img_path]:
            return False
        
        try:
            base_name = os.path.splitext(os.path.basename(img_path))[0]
            
            if overwrite:
                # Save directly in current folder
                xml_path = os.path.join(self.folder, f"{base_name}.xml")
            else:
                # Save in annotations folder
                xml_path = os.path.join(output_folder, f"{base_name}.xml")
            
            # Convert annotations to XML format
            xml_content = self.convert_annotations_to_xml_format(img_path, self.annotations[img_path])
            
            if xml_content:
                with open(xml_path, 'w', encoding='utf-8') as f:
                    f.write(xml_content)
                
                print(f"Saved XML annotations: {xml_path}")
                return True
        
        except Exception as e:
            print(f"Error saving XML for {img_path}: {e}")
            return False
        
        return False

    def show_help(self):
        help_text = """
            <h2>Annotation Tool - User Guide</h2>

            <h3>📁 Getting Started</h3>
            <ul>
            <li>Click <b>'Open Image Folder'</b> to load images for annotation</li>
            <li>Click <b>'Open Folder with Images & Annotations'</b> to load both images and their annotation files</li>
            <li>Images will appear as thumbnails at the bottom</li>
            <li>Click any thumbnail to select an image</li>
            </ul>

            <h3>🎯 Annotation Tools</h3>
            <ul>
            <li><b>Rectangle Tool (R):</b> Click and drag to create bounding boxes</li>
            <li><b>Polygon Tool (P):</b> Click to place points, right-click or use 'Finish Polygon' to complete</li>
            <li><b>Select Tool (S):</b> Click and drag to move annotations, drag corners to resize</li>
            </ul>

            <h3>🔧 Basic Operations</h3>
            <ul>
            <li><b>Enter Label:</b> Type the object label before annotating</li>
            <li><b>Label Selection:</b> Click the 📋 button to select from existing labels</li>
            <li><b>Clear All:</b> Remove all annotations from current image</li>
            <li><b>Navigation:</b> Use Previous/Next buttons (A/D keys) or click thumbnails</li>
            </ul>

            <h3>🔄 Annotation Editing</h3>
            <ul>
            <li><b>Auto-Label Editor:</b> Label selection opens automatically after creating annotations</li>
            <li><b>Edit Label (E):</b> Modify selected annotation's label</li>
            <li><b>Copy (Ctrl+C):</b> Copy selected annotation</li>
            <li><b>Paste (Ctrl+V):</b> Paste copied annotation</li>
            <li><b>Delete Selected (Delete/Ctrl+D):</b> Remove currently selected annotation</li>
            <li><b>Click and Drag:</b> Move annotations or resize using handles</li>
            </ul>

            <h3>↩️ Undo/Redo</h3>
            <ul>
            <li><b>Undo (Ctrl+Z):</b> Reverse last action</li>
            <li><b>Redo (Ctrl+Y):</b> Restore undone action</li>
            </ul>

            <h3>🔍 Zoom & View</h3>
            <ul>
            <li><b>Zoom In/Out:</b> Use buttons or Ctrl+Mouse Wheel</li>
            <li><b>Fit to Window:</b> Auto-adjust image to window size</li>
            <li><b>Pan:</b> Use scrollbars when zoomed in</li>
            </ul>

            <h3>💾 Saving Annotations</h3>
            <ul>
            <li><b>Auto-Save:</b> Annotations are automatically saved in memory</li>
            <li><b>Save Current:</b> Save annotations for current image only (choose JSON or XML format)</li>
            <li><b>Overwrite Existing Files:</b> Update annotation files in current folder (choose JSON or XML format)</li>
            <li><b>Final Save & Verify:</b> Review all annotations before export to new folder (choose JSON or XML format)</li>
            <li><b>Format Selection:</b> When saving, you can choose between JSON or XML format</li>
            <li><b>JSON Format:</b> LabelMe compatible format with image data and annotations</li>
            <li><b>XML Format:</b> Pascal VOC format compatible with popular object detection frameworks</li>
            </ul>

            <h3>🎨 Interface Features</h3>
            <ul>
            <li>Different colors for different labels</li>
            <li>Real-time annotation display</li>
            <li>Progress tracking with auto-save status</li>
            <li>Visual indicators for annotated images in thumbnails</li>
            <li>Dark theme for comfortable usage</li>
            <li>Tooltips on all buttons for quick guidance</li>
            <li>Format selection dialog for flexible export options</li>
            </ul>

            <h3>⚡ Keyboard Shortcuts</h3>
            <ul>
            <li><b>A / Left Arrow:</b> Previous image</li>
            <li><b>D / Right Arrow:</b> Next image</li>
            <li><b>R:</b> Rectangle tool</li>
            <li><b>P:</b> Polygon tool</li>
            <li><b>S:</b> Select tool</li>
            <li><b>E:</b> Edit selected annotation label</li>
            <li><b>Delete / Ctrl+D:</b> Delete selected annotation</li>
            <li><b>Ctrl+C:</b> Copy selected annotation</li>
            <li><b>Ctrl+V:</b> Paste annotation</li>
            <li><b>Ctrl+Z:</b> Undo</li>
            <li><b>Ctrl+Y:</b> Redo</li>
            <li><b>Escape:</b> Cancel current operation</li>
            <li><b>Ctrl + Mouse Wheel:</b> Zoom in/out</li>
            <li><b>Right-click:</b> Finish polygon (when using polygon tool)</li>
            </ul>

            <h3>📊 JSON Export Format</h3>
            <ul>
            <li><b>imagePath:</b> Full path to the image</li>
            <li><b>imageName:</b> Just the filename</li>
            <li><b>imageData:</b> Base64 encoded image data</li>
            <li><b>imageWidth / imageHeight:</b> Image dimensions</li>
            <li><b>annotations:</b> All annotation data with labels and coordinates</li>
            <li><b>exportTime / updatedTime:</b> Timestamps</li>
            <li><b>Compatible with:</b> LabelMe and custom annotation pipelines</li>
            </ul>

            <h3>📄 XML Export Format (Pascal VOC)</h3>
            <ul>
            <li><b>&lt;folder&gt;:</b> Name of the folder containing the image</li>
            <li><b>&lt;filename&gt;:</b> Name of the image file</li>
            <li><b>&lt;path&gt;:</b> Full path to the image file</li>
            <li><b>&lt;size&gt;:</b> Image dimensions (width, height, depth)</li>
            <li><b>&lt;object&gt;:</b> Each annotation as a separate object</li>
            <li><b>&lt;name&gt;:</b> Label name for the object</li>
            <li><b>&lt;bndbox&gt;:</b> Bounding box coordinates (xmin, ymin, xmax, ymax)</li>
            <li><b>&lt;pose&gt;, &lt;truncated&gt;, &lt;difficult&gt;:</b> Standard Pascal VOC attributes</li>
            <li><b>Compatible with:</b> Popular object detection frameworks like YOLO, Faster R-CNN, SSD</li>
            </ul>

            <h3>🔄 Format Comparison</h3>
            <ul>
            <li><b>JSON:</b> Better for web applications, includes image data, smaller file size</li>
            <li><b>XML:</b> Industry standard for object detection, compatible with most ML frameworks</li>
            <li><b>Both formats</b> contain the same annotation information</li>
            <li>You can export in both formats for different use cases</li>
            </ul>
            """
        
        # Create a custom dialog with scrollable text
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Help - Annotation Tool User Guide")
        dialog.setModal(True)
        dialog.resize(600, 500)
        
        # Create layout
        layout = QtWidgets.QVBoxLayout(dialog)
        
        # Create scroll area
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        
        # Create content widget
        content_widget = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content_widget)
        
        # Create text browser for HTML content
        text_browser = QtWidgets.QTextBrowser()
        text_browser.setHtml(help_text)
        text_browser.setOpenExternalLinks(False)
        text_browser.setReadOnly(True)
        
        # Add text browser to content layout
        content_layout.addWidget(text_browser)
        
        # Set content widget to scroll area
        scroll_area.setWidget(content_widget)
        
        # Add scroll area to main layout
        layout.addWidget(scroll_area)
        
        # Add OK button
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)
        
        # Show dialog
        dialog.exec_()
    def browse_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Image Folder")
        if folder:
            self.load_folder(folder)
                
    def load_folder(self, folder):
        self.folder = folder
        exts = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp")
        self.images = sorted([os.path.join(folder, f) for f in os.listdir(folder) 
                            if f.lower().endswith(exts)])
        
        if self.images:
            self.thumbnail_list.load_images(self.images)
            self.current_index = 0
            
            # Auto-load any existing annotations in the folder
            self.auto_load_existing_annotations()
            
            self.load_current_image()
            self.update_annotated_count()

    def auto_load_existing_annotations(self):
        """Automatically load existing annotations when opening a folder"""
        for img_path in self.images:
            img_base_name = os.path.splitext(os.path.basename(img_path))[0]
            
            # Look for JSON files with same base name
            possible_json_names = [
                f"{img_base_name}.json",
                f"{img_base_name.lower()}.json",
                f"{img_base_name.upper()}.json"
            ]
            
            for json_name in possible_json_names:
                json_path = os.path.join(self.folder, json_name)
                if os.path.exists(json_path):
                    try:
                        with open(json_path, 'r') as f:
                            data = json.load(f)
                            
                            # Handle both LabelMe format and legacy custom format
                            annotations = []
                            
                            # LabelMe format
                            if 'shapes' in data:
                                shapes = data.get('shapes', [])
                                for shape in shapes:
                                    annotation = {
                                        'label': shape.get('label', 'unknown'),
                                        'shape': shape.get('shape_type', 'polygon'),
                                        'points': shape.get('points', [])
                                    }
                                    annotations.append(annotation)
                            # Legacy custom format (for backward compatibility)
                            elif 'annotations' in data:
                                annotations = data.get('annotations', [])
                            
                            if annotations:
                                self.annotations[img_path] = annotations
                                
                                # Extract labels
                                for ann in annotations:
                                    self.existing_labels.add(ann['label'])
                                break  # Found annotations, no need to check other names
                    except Exception as e:
                        print(f"Error auto-loading annotations from {json_path}: {e}")

    def load_folder_with_annotations(self):
        """Load a folder that contains both images and annotation JSON files"""
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Folder with Images and Annotations")
        if folder:
            self.folder = folder
            self.images = []
            self.annotations = {}
            self.existing_labels.clear()
            
            # Find all image files
            exts = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp")
            self.images = sorted([os.path.join(folder, f) for f in os.listdir(folder) 
                                if f.lower().endswith(exts)])
            
            if not self.images:
                QtWidgets.QMessageBox.warning(self, "No Images", "No image files found in the selected folder")
                return
            
            # Load thumbnails
            self.thumbnail_list.load_images(self.images)
            self.current_index = 0
            
            # Load annotations from JSON files in the same folder
            self.load_annotations_from_current_folder()
            
            self.load_current_image()
            self.update_annotated_count()
            
            QtWidgets.QMessageBox.information(self, "Folder Loaded", 
                                            f"Loaded {len(self.images)} images\n"
                                            f"Found annotations for {len([img for img in self.images if img in self.annotations])} images\n"
                                            f"Found {len(self.existing_labels)} unique labels")

    def load_annotations_from_current_folder(self):
        """Load annotations from JSON files in the current folder"""
        if not self.folder:
            return
        
        loaded_count = 0
        
        # Find all JSON files in the folder
        try:
            json_files = [f for f in os.listdir(self.folder) if f.endswith('.json')]
        except Exception as e:
            print(f"Error reading folder {self.folder}: {e}")
            return
        
        for json_file in json_files:
            json_path = os.path.join(self.folder, json_file)
            try:
                with open(json_path, 'r') as f:
                    data = json.load(f)
                    
                    # Detect JSON format and extract annotations accordingly
                    annotations = []
                    image_name_from_json = ""
                    
                    # LabelMe format (new format)
                    if 'shapes' in data and 'imagePath' in data:
                        shapes = data.get('shapes', [])
                        for shape in shapes:
                            annotation = {
                                'label': shape.get('label', 'unknown'),
                                'shape': shape.get('shape_type', 'polygon'),
                                'points': shape.get('points', [])
                            }
                            annotations.append(annotation)
                        image_name_from_json = data.get('imagePath', '')
                        # Ensure we have just the filename
                        image_name_from_json = os.path.basename(image_name_from_json)
                        
                    # Legacy custom format (for backward compatibility)
                    elif 'annotations' in data and 'image_path' in data:
                        annotations = data.get('annotations', [])
                        image_name_from_json = data.get('image_path', '')
                        # Ensure we have just the filename
                        image_name_from_json = os.path.basename(image_name_from_json)
                    
                    else:
                        print(f"Unknown JSON format in {json_file}")
                        continue
                    
                    if not annotations:
                        print(f"No annotations found in {json_file}")
                        continue
                    
                    # Find matching image
                    matching_image = None
                    json_base_name = os.path.splitext(json_file)[0]
                    
                    # Method 1: Try filename matching with the stored image_name_from_json
                    if image_name_from_json:
                        for img in self.images:
                            img_filename = os.path.basename(img)
                            if img_filename == image_name_from_json:
                                matching_image = img
                                break
                    
                    # Method 2: Try base name matching (without extension)
                    if not matching_image:
                        for img in self.images:
                            img_base_name = os.path.splitext(os.path.basename(img))[0]
                            if img_base_name == json_base_name:
                                matching_image = img
                                break
                    
                    # Method 3: Try case-insensitive base name matching
                    if not matching_image:
                        for img in self.images:
                            img_base_name = os.path.splitext(os.path.basename(img))[0]
                            if img_base_name.lower() == json_base_name.lower():
                                matching_image = img
                                break
                    
                    # Method 4: Try case-insensitive filename matching with image_name_from_json
                    if not matching_image and image_name_from_json:
                        for img in self.images:
                            img_filename = os.path.basename(img)
                            if img_filename.lower() == image_name_from_json.lower():
                                matching_image = img
                                break
                    
                    if matching_image:
                        # Store annotations in memory
                        self.annotations[matching_image] = annotations
                        loaded_count += 1
                        
                        # Extract labels
                        for ann in annotations:
                            self.existing_labels.add(ann['label'])
                    else:
                        print(f"Could not find matching image for {json_file}. Looking for: {image_name_from_json}")
                            
            except Exception as e:
                print(f"Error loading {json_path}: {e}")

    def auto_open_label_editor(self):
        """Automatically open label selection after creating an annotation"""
        if self.canvas.shapes and self.canvas.selected_shape_index == -1:
            # Select the last created annotation
            self.canvas.selected_shape_index = len(self.canvas.shapes) - 1
            # DIRECTLY OPEN FULL LABEL SELECTION DIALOG
            self.show_label_selection_after_annotation()

    def show_label_selection_after_annotation(self):
        """Show label selection dialog immediately after annotation creation"""
        if self.canvas.selected_shape_index != -1:
            current_label = self.canvas.shapes[self.canvas.selected_shape_index][2]
            
            # Directly open the full label selection dialog
            dialog = LabelSelectionDialog(sorted(self.existing_labels), self)
            dialog.label_input.setText(current_label)  # Pre-fill with current label
            dialog.label_input.selectAll()  # Select text for easy editing
            
            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                new_label = dialog.get_selected_label()
                if new_label and new_label != current_label:
                    self.canvas.edit_selected_label(new_label)
                    self.existing_labels.add(new_label)
                    # Update the label input field in main UI
                    self.label_input.setText(new_label)

    def load_current_image(self):
        """Load current image and its annotations - FIXED VERSION"""
        if not self.images or self.current_index < 0 or self.current_index >= len(self.images):
            return
            
        try:
            # Set current image FIRST - THIS WAS MISSING
            img_path = self.images[self.current_index]
            self.current_image = img_path  # THIS FIXES THE "No current image" ERROR
            
            
            # Load the image to canvas
            pixmap = QtGui.QPixmap(img_path)
            if pixmap.isNull():
                print(f"Failed to load image: {img_path}")
                return
                
            self.canvas.load_image(img_path)
            self.canvas.setEnabled(True)
            
            # Update window title
            self.setWindowTitle(f"Annotation Tool - {os.path.basename(img_path)} ({self.current_index + 1}/{len(self.images)})")
            
            # Load annotations AFTER image is loaded
            self.load_annotations()
            
            # Update thumbnail selection
            self.thumbnail_list.setCurrentRow(self.current_index)
            
        except Exception as e:
            print(f"Error loading current image: {e}")
            import traceback
            traceback.print_exc()

    def auto_save_annotations(self):
        """Automatically save annotations for current image"""
        if not self.auto_save_enabled:
            return
            
        if hasattr(self, 'current_image') and self.current_image:
            img_path = self.current_image
            
            # Get current annotations from canvas
            annotations = self.canvas.get_annotations()
            if annotations:
                self.annotations[img_path] = annotations
                self.pending_saves.add(img_path)
                self.update_annotated_count()

    def save_and_overwrite(self):
        """Save all annotations and overwrite existing files with format selection"""
        # First, auto-save any pending changes
        for i in range(len(self.images)):
            self.current_index = i
            self.load_current_image()
            self.auto_save_annotations()
        
        # Ask for save format
        format_choice = self.ask_save_format()
        if format_choice is None:
            return  # User cancelled
        
        # Show confirmation dialog
        format_name = "JSON" if format_choice == "json" else "XML"
        reply = QtWidgets.QMessageBox.question(self, "Confirm Overwrite",
                                            f"This will overwrite all existing annotation files in the current folder as {format_name} format.\n\n"
                                            "Are you sure you want to continue?",
                                            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                            QtWidgets.QMessageBox.No)
        
        if reply == QtWidgets.QMessageBox.No:
            return
        
        saved_count = 0
        error_count = 0
        
        # Save each annotated image directly in the current folder
        for img_path in self.images:
            if img_path in self.annotations and self.annotations[img_path]:
                try:
                    if format_choice == "json":
                        success = self.save_annotations_as_json(img_path, self.folder, overwrite=True)
                    else:  # xml
                        success = self.save_annotations_as_xml(img_path, self.folder, overwrite=True)
                    
                    if success:
                        saved_count += 1
                    else:
                        error_count += 1
                        
                except Exception as e:
                    print(f"Error saving {img_path}: {e}")
                    error_count += 1
        
        # Clear pending saves
        self.pending_saves.clear()
        
        # Show results
        msg = QtWidgets.QMessageBox(self)
        msg.setWindowTitle("Save Complete")
        msg.setIcon(QtWidgets.QMessageBox.Information)
        
        if error_count == 0:
            msg.setText(f"✅ Successfully overwrote {saved_count} {format_name} annotation files!")
            msg.setInformativeText(f"Location: {self.folder}")
        else:
            msg.setText(f"✅ Overwrote {saved_count} {format_name} annotations with {error_count} errors.")
            msg.setInformativeText(f"Check the console for details.\nLocation: {self.folder}")
        
        msg.exec_()
                        
    def thumbnail_clicked(self, item):
        path = item.data(QtCore.Qt.UserRole)
        if path in self.images:
            self.save_current_annotations()
            self.current_index = self.images.index(path)
            self.load_current_image()
            
    def prev_image(self):
        if self.current_index > 0:
            self.save_current_annotations()
            self.current_index -= 1
            self.load_current_image()
            
    def next_image(self):
        if self.current_index < len(self.images) - 1:
            self.save_current_annotations()
            self.current_index += 1
            self.load_current_image()
            
    def change_mode(self, mode):
        mode_map = {"Rectangle": "rect", "Polygon": "polygon", "Select": "select"}
        self.canvas.set_mode(mode_map.get(mode, "rect"))
        
    def update_current_label(self, label):
        self.canvas.set_label(label)
        if label:
            self.existing_labels.add(label)
        
    def set_label(self, label):
        self.label_input.setText(label)
        self.canvas.set_label(label)
        if label:
            self.existing_labels.add(label)
        
    def show_label_selection(self):
        dialog = LabelSelectionDialog(sorted(self.existing_labels), self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            label = dialog.get_selected_label()
            if label:
                self.set_label(label)
        
    def edit_selected_label(self):
        """Edit the label of the selected annotation - direct to full selection"""
        if self.canvas.selected_shape_index != -1:
            current_label = self.canvas.shapes[self.canvas.selected_shape_index][2]
            
            # Directly open the full label selection dialog
            dialog = LabelSelectionDialog(sorted(self.existing_labels), self)
            dialog.label_input.setText(current_label)  # Pre-fill with current label
            dialog.label_input.selectAll()  # Select text for easy editing
            
            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                new_label = dialog.get_selected_label()
                if new_label and new_label != current_label:
                    self.canvas.edit_selected_label(new_label)
                    self.existing_labels.add(new_label)
                    # Update the label input field in main UI
                    self.label_input.setText(new_label)
        else:
            QtWidgets.QMessageBox.warning(self, "No Selection", "Please select an annotation first")

    def finish_polygon(self):
        self.canvas.finish_polygon()
        
    def clear_annotations(self):
        self.canvas.clear_annotations()
        
    def delete_selected(self):
        self.canvas.delete_selected_shape()
        
    def copy_selected(self):
        self.canvas.copy_selected_shape()
        
    def paste_shape(self):
        self.canvas.paste_shape()
        
    def zoom_in(self):
        self.canvas.zoom_in()
        
    def zoom_out(self):
        self.canvas.zoom_out()
        
    def fit_to_window(self):
        self.canvas.fit_to_window()
        
    def undo(self):
        self.canvas.undo()
        
    def redo(self):
        self.canvas.redo()
   
    def update_thumbnail_status(self):
        for i in range(self.thumbnail_list.count()):
            item = self.thumbnail_list.item(i)
            img_path = item.data(QtCore.Qt.UserRole)
            
            if img_path in self.annotations and self.annotations[img_path]:
                item.setBackground(QtGui.QColor(76, 175, 80))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                ann_count = len(self.annotations[img_path])
                item.setText(f"{os.path.basename(img_path)} ({ann_count})")
            else:
                item.setBackground(QtGui.QColor(69, 69, 88))
                font = item.font()
                font.setBold(False)
                item.setFont(font)
                item.setText(os.path.basename(img_path))
        
    def save_current_annotations(self):
        if 0 <= self.current_index < len(self.images):
            annotations = self.canvas.get_annotations()
            if annotations:
                self.annotations[self.images[self.current_index]] = annotations
                self.pending_saves.add(self.images[self.current_index])
                self.update_annotated_count()
                self.update_thumbnail_status()
                
    def save_current(self):
        """Save current annotations with format selection"""
        self.save_current_annotations()
        
        # Ask for save format first
        format_choice = self.ask_save_format()
        if format_choice is None:
            return  # User cancelled
        
        # Ask user if they want to overwrite or create new
        reply = QtWidgets.QMessageBox.question(self, "Save Current",
                                            "How do you want to save?\n\n"
                                            "Yes: Overwrite in current folder\n"
                                            "No: Save in new annotations folder",
                                            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel,
                                            QtWidgets.QMessageBox.No)
        
        if reply == QtWidgets.QMessageBox.Yes:
            # Overwrite in current folder
            if self.save_annotations_to_file(self.images[self.current_index], overwrite=True, format_choice=format_choice):
                format_name = "JSON" if format_choice == "json" else "XML"
                QtWidgets.QMessageBox.information(self, "Saved", f"Current annotations saved as {format_name}!")
        elif reply == QtWidgets.QMessageBox.No:
            # Save in new folder
            if self.save_annotations_to_file(self.images[self.current_index], overwrite=False, format_choice=format_choice):
                format_name = "JSON" if format_choice == "json" else "XML"
                QtWidgets.QMessageBox.information(self, "Saved", f"Current annotations saved as {format_name} in new folder!")
        # else: Cancel - do nothing
        
    def save_all(self):
        for i in range(len(self.images)):
            self.current_index = i
            self.load_current_image()
            self.auto_save_annotations()
        
        self.enable_final_verification_mode()

    def enable_final_verification_mode(self):
        self.final_save_mode = True
        self.auto_save_enabled = False
        
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Final Verification - Review All Annotations")
        dialog.setMinimumSize(700, 500)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #2D2D3C;
                color: white;
            }
            QPushButton {
                background-color: #4A90E2;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 4px;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: #5BA0F0;
            }
            QListWidget {
                background-color: #454558;
                color: white;
                border: 1px solid #555;
            }
        """)
        
        layout = QtWidgets.QVBoxLayout(dialog)
        
        title = QtWidgets.QLabel("📋 Final Annotation Review")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #4A90E2; margin: 10px;")
        layout.addWidget(title)
        
        annotated_count = sum(1 for img_path in self.images 
                             if img_path in self.annotations and self.annotations[img_path])
        summary = QtWidgets.QLabel(f"📊 Annotated Images: {annotated_count}/{len(self.images)}")
        summary.setStyleSheet("margin: 10px; font-weight: bold;")
        layout.addWidget(summary)
        
        list_widget = QtWidgets.QListWidget()
        list_widget.setIconSize(QtCore.QSize(50, 50))
        
        for img_path in self.images:
            item = QtWidgets.QListWidgetItem(os.path.basename(img_path))
            
            pixmap = QtGui.QPixmap(img_path)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(50, 50, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                item.setIcon(QtGui.QIcon(scaled_pixmap))
            
            if img_path in self.annotations and self.annotations[img_path]:
                ann_count = len(self.annotations[img_path])
                item.setText(f"{os.path.basename(img_path)} ({ann_count} annotations)")
                item.setBackground(QtGui.QColor(76, 175, 80))
            else:
                item.setBackground(QtGui.QColor(244, 67, 54))
            
            item.setData(QtCore.Qt.UserRole, img_path)
            list_widget.addItem(item)
        
        layout.addWidget(list_widget)
        
        list_widget.itemDoubleClicked.connect(lambda item: self.view_image_for_verification(item.data(QtCore.Qt.UserRole)))
        
        button_layout = QtWidgets.QHBoxLayout()
        
        btn_save_all = QtWidgets.QPushButton("💾 Save All Annotations to Folder")
        btn_save_all.clicked.connect(lambda: self.final_save_all_annotations(dialog))
        
        btn_cancel = QtWidgets.QPushButton("Cancel Verification")
        btn_cancel.clicked.connect(dialog.reject)
        
        btn_continue = QtWidgets.QPushButton("Continue Annotating")
        btn_continue.clicked.connect(lambda: self.continue_annotating(dialog))
        
        button_layout.addWidget(btn_cancel)
        button_layout.addWidget(btn_continue)
        button_layout.addWidget(btn_save_all)
        
        layout.addLayout(button_layout)
        
        dialog.exec_()

    def view_image_for_verification(self, img_path):
        if img_path in self.images:
            self.current_index = self.images.index(img_path)
            self.load_current_image()
            self.mode_combo.setCurrentText("Select")

    def continue_annotating(self, dialog):
        self.final_save_mode = False
        self.auto_save_enabled = True
        dialog.accept()

    def final_save_all_annotations(self, dialog):
        # Ask for save format
        format_choice = self.ask_save_format()
        if format_choice is None:
            return  # User cancelled
        
        current_time = QtCore.QDateTime.currentDateTime().toString("yyyy-MM-dd_HH-mm-ss")
        format_ext = "json" if format_choice == "json" else "xml"
        main_annot_folder = os.path.join(self.folder, f"annotations_{format_ext}_{current_time}")
        os.makedirs(main_annot_folder, exist_ok=True)
        
        saved_count = 0
        error_count = 0
        
        for img_path in self.images:
            if img_path in self.annotations and self.annotations[img_path]:
                try:
                    if format_choice == "json":
                        success = self.save_annotations_as_json(img_path, main_annot_folder, overwrite=False)
                    else:  # xml
                        success = self.save_annotations_as_xml(img_path, main_annot_folder, overwrite=False)
                    
                    if success:
                        # Copy original image
                        base_name = os.path.splitext(os.path.basename(img_path))[0]
                        original_extension = os.path.splitext(img_path)[1].lower()
                        image_copy_path = os.path.join(main_annot_folder, f"{base_name}{original_extension}")
                        shutil.copy2(img_path, image_copy_path)
                        
                        saved_count += 1
                    else:
                        error_count += 1
                        
                except Exception as e:
                    print(f"Error saving {img_path}: {e}")
                    error_count += 1
        
        self.pending_saves.clear()
        
        msg = QtWidgets.QMessageBox(self)
        msg.setWindowTitle("Save Complete")
        msg.setIcon(QtWidgets.QMessageBox.Information)
        
        format_name = "JSON" if format_choice == "json" else "XML"
        if error_count == 0:
            msg.setText(f"✅ Successfully saved {saved_count} {format_name} annotations!")
            msg.setInformativeText(f"Location: {main_annot_folder}")
        else:
            msg.setText(f"✅ Saved {saved_count} {format_name} annotations with {error_count} errors.")
            msg.setInformativeText(f"Check the console for details.\nLocation: {main_annot_folder}")
        
        msg.exec_()
        
        self.final_save_mode = False
        self.auto_save_enabled = True
        dialog.accept()
    
        
    def save_annotations_to_file(self, img_path, overwrite=False, format_choice="json"):
        """Save annotations to file in selected format (JSON or XML)"""
        if img_path not in self.annotations or not self.annotations[img_path]:
            return False
        
        if overwrite:
            # Save directly in current folder
            output_folder = self.folder
        else:
            # Save in annotations folder
            if not self.annotation_folder:
                current_time = QtCore.QDateTime.currentDateTime().toString("yyyy-MM-dd_HH-mm")
                self.annotation_folder = f"annotations_{current_time}"
            output_folder = os.path.join(self.folder, self.annotation_folder)
            os.makedirs(output_folder, exist_ok=True)
        
        if format_choice == "json":
            return self.save_annotations_as_json(img_path, output_folder, overwrite)
        elif format_choice == "xml":
            return self.save_annotations_as_xml(img_path, output_folder, overwrite)
        else:
            print(f"Unknown format: {format_choice}")
            return False

    def save_annotations_as_json(self, img_path, output_folder, overwrite=False):
        """Save annotations as JSON file in LabelMe format"""
        if img_path not in self.annotations or not self.annotations[img_path]:
            return False
        
        try:
            base_name = os.path.splitext(os.path.basename(img_path))[0]
            
            if overwrite:
                json_path = os.path.join(self.folder, f"{base_name}.json")
            else:
                json_path = os.path.join(output_folder, f"{base_name}.json")
            
            image_name = os.path.basename(img_path)
            
            # Get image data as base64
            image_data = ""
            try:
                with open(img_path, 'rb') as img_file:
                    image_bytes = img_file.read()
                    image_data = base64.b64encode(image_bytes).decode('utf-8')
            except Exception as e:
                print(f"Error encoding image data: {e}")
            
            # Convert to LabelMe format
            shapes = []
            for ann in self.annotations[img_path]:
                # Convert points to floats
                float_points = []
                for point in ann['points']:
                    if isinstance(point, (list, tuple)) and len(point) >= 2:
                        float_points.append([float(point[0]), float(point[1])])
                
                shape = {
                    "label": ann['label'],
                    "points": float_points,
                    "group_id": None,
                    "description": "",
                    "shape_type": ann['shape'],
                    "flags": {},
                    "mask": None
                }
                shapes.append(shape)
            
            annotation_data = {
                "version": "5.8.2",
                "flags": {},
                "shapes": shapes,
                "imagePath": image_name,
                "imageData": image_data,
                "imageHeight": self.canvas.original_pixmap.height(),
                "imageWidth": self.canvas.original_pixmap.width()
            }
            
            # Add custom fields for tracking
            if not overwrite:
                annotation_data['export_time'] = QtCore.QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
            else:
                annotation_data['updated_time'] = QtCore.QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
                annotation_data['updated'] = True
            
            with open(json_path, 'w') as f:
                json.dump(annotation_data, f, indent=2)
            
            # Save original image (only for new folders, not for overwrites)
            if not overwrite:
                self.save_original_image(img_path, output_folder)
            
            return True
            
        except Exception as e:
            print(f"Error saving JSON for {img_path}: {e}")
            return False

    def save_original_image(self, img_path, output_folder):
        base_name = os.path.splitext(os.path.basename(img_path))[0]
        original_extension = os.path.splitext(img_path)[1].lower()
        output_path = os.path.join(output_folder, f"{base_name}{original_extension}")
        shutil.copy2(img_path, output_path)
        
    def load_annotations(self):
        """Load annotations for current image and display them on canvas - FIXED"""
        if not hasattr(self, 'current_image') or not self.current_image:
            return
            
        
        img_path = self.current_image
        if img_path in self.annotations:
            annotations = self.annotations[img_path]
            
            # Clear current shapes and load new ones
            self.canvas.shapes.clear()
            
            for i, ann in enumerate(annotations):
                try:
                    
                    if ann['shape'] == 'rectangle':
                        points = ann['points']
                        
                        if len(points) >= 2:
                            # Convert points to QPoints
                            point1 = QtCore.QPoint(int(points[0][0]), int(points[0][1]))
                            point2 = QtCore.QPoint(int(points[1][0]), int(points[1][1]))
                            
                            # Add to canvas shapes
                            self.canvas.shapes.append(('rect', [point1, point2], ann['label']))
                            
                    elif ann['shape'] == 'polygon':
                        qpoints = []
                        for point in ann['points']:
                            if len(point) >= 2:
                                qpoints.append(QtCore.QPoint(int(point[0]), int(point[1])))
                        
                        
                        if len(qpoints) >= 3:
                            # Add to canvas shapes
                            self.canvas.shapes.append(('polygon', qpoints, ann['label']))
                            
                except Exception as e:
                    print(f"load_annotations: Error in annotation {i}: {e}")
                    continue
        else:
            self.canvas.update()
            
    def update_annotated_count(self):
        annotated = sum(1 for img_path in self.images 
                       if img_path in self.annotations and self.annotations[img_path])
        pending = len(self.pending_saves)
        status = f"Annotated: {annotated}/{len(self.images)}"
        if pending > 0:
            status += f" (Auto-saved: {pending})"
        self.annotated_count_label.setText(status)

    def apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #2D2D3C;
                color: white;
            }
            QGroupBox {
                color: white;
                border: 2px solid #444;
                border-radius: 5px;
                margin-top: 1ex;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QPushButton {
                background-color: #2d7ef1;
                color: white;
                border: none;
                padding: 6px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #5BA0F0;
            }
            QPushButton:pressed {
                background-color: #3A80D2;
            }
            QLineEdit, QComboBox {
                background-color: #454558;
                color: white;
                border: 1px solid #555;
                padding: 4px;
                border-radius: 3px;
                font-size: 11px;
            }
            QListWidget {
                background-color: #454558;
                color: white;
                border: 1px solid #555;
            }
            QScrollArea {
                border: 1px solid #555;
            }
        """)
        
    def setup_shortcuts(self):
        # Navigation shortcuts
        QtWidgets.QShortcut(QtGui.QKeySequence("A"), self, self.prev_image)
        QtWidgets.QShortcut(QtGui.QKeySequence("D"), self, self.next_image)
        QtWidgets.QShortcut(QtGui.QKeySequence("Left"), self, self.prev_image)
        QtWidgets.QShortcut(QtGui.QKeySequence("Right"), self, self.next_image)
        
        # Tool shortcuts
        QtWidgets.QShortcut(QtGui.QKeySequence("R"), self, lambda: self.mode_combo.setCurrentText("Rectangle"))
        QtWidgets.QShortcut(QtGui.QKeySequence("P"), self, lambda: self.mode_combo.setCurrentText("Polygon"))
        QtWidgets.QShortcut(QtGui.QKeySequence("S"), self, lambda: self.mode_combo.setCurrentText("Select"))
        
        # ADD LABEL EDIT SHORTCUT
        QtWidgets.QShortcut(QtGui.QKeySequence("E"), self, self.edit_selected_label)
        QtWidgets.QShortcut(QtGui.QKeySequence("Delete"), self, self.delete_selected)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+D"), self, self.delete_selected)
        QtWidgets.QShortcut(QtGui.QKeySequence("F5"), self, self.refresh_current_annotations)

    def refresh_current_annotations(self):
        """Force refresh of current image annotations"""
        if 0 <= self.current_index < len(self.images):
            img_path = self.images[self.current_index]
            # Clear from memory to force reload from file
            if img_path in self.annotations:
                del self.annotations[img_path]
            self.load_current_image()
            QtWidgets.QMessageBox.information(self, "Refreshed", "Annotations refreshed from file!")

    def initialize_tool(self):
        """Optional initialization method called when widget is loaded"""
        print("Annotation tool initialized")

# Keep the standalone version for running separately
class AnnotationStandaloneWindow(QtWidgets.QMainWindow):
    """Wrapper to run annotation tool as standalone window"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Advanced Annotation Tool")
        self.resize(1200, 800)
        
        annotation_widget = AnnotationTool()
        self.setCentralWidget(annotation_widget)

def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')
    
    font = QtGui.QFont("Segoe UI", 10)
    app.setFont(font)
    
    window = AnnotationStandaloneWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()