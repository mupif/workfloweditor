#
#           MuPIF: Multi-Physics Integration Framework
#               Copyright (C) 2010-2015 Borek Patzak
#
#    Czech Technical University, Faculty of Civil Engineering,
#  Department of Structural Mechanics, 166 29 Prague, Czech Republic
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor,
# Boston, MA  02110-1301  USA
#


from PyQt5 import QtGui
from PyQt5 import QtCore
from PyQt5 import QtWidgets
import uuid
import helpers
from exceptions import DuplicateKnobNameError, KnobConnectionError
import json
import os

windows = os.name == "nt"
DELETE_MODIFIER_KEY = QtCore.Qt.AltModifier if windows else QtCore.Qt.ControlModifier


"""
 data structure for workflow editor

 The execution model is based on idea of combining ExecucutionBlocks
 Each block represents specific action or procedure and it is responsible
 for generating its code.
 The execution blocks can be composed/contain other blocks
 (an example is a time loop block, which contains blocks to be executed
  within a time loop)
 Each execution block can define its input and output slots, basically
 representing input and output parameters of particular block.
 The input/output slots can be connected using DataLink objects.

"""

#
# Data model
#
#


class DataProvider:
    def __init__(self):
        """Constructor"""

    def get(self, slot=None):
        """Returns the value associated with DataSlot"""
        return None

    def getOutputSlots(self):
        """Returns a list of output DataSlots"""
        return []


class DataConsumer:
    def __init__(self):
        """Constructor"""

    def set(self, value, slot=None):
        """sets the value associated with DataSlot"""
        return

    def getInputSlots(self):
        """Returns list of input DataSlots"""
        return []


# Currently only affects Knob label placement.
FLOW_LEFT_TO_RIGHT = "flow_left_to_right"
FLOW_RIGHT_TO_LEFT = "flow_right_to_left"


class DataSlot(QtWidgets.QGraphicsItem):
    """
    Class describing input/output parameter of block
    """
    def __init__(self, owner, name, type, optional=False, parent=None, **kwargs):
        QtWidgets.QGraphicsItem.__init__(self, parent)
        self.name = name
        self.owner = owner
        self.type = type
        self.optional = optional
        if isinstance(self, OutputDataSlot):
            self.optional = True
        self.uuid = str(uuid.uuid4())

        self.dataLinks = []  # data
        self.hover = False

        # Qt
        self.x = 0
        self.y = 0
        self.w = 14
        self.h = 14

        self.spacing = 5
        self.flow = FLOW_LEFT_TO_RIGHT

        self.maxConnections = -1  # A negative value means 'unlimited'.
        self.displayName = self.name

        self.labelColor = QtGui.QColor(10, 10, 10)

        self.fillColor_not_connected = QtGui.QColor(255, 50, 50)
        self.fillColor_regular = QtGui.QColor(100, 100, 100)
        self.fillColor_optional = QtGui.QColor(50, 200, 50)
        self.fillColor_highlight = QtGui.QColor(255, 255, 0)
        self.fillColor = self.fillColor_regular
        self.updateColor()

        # Temp store for DataLink currently being created.
        self.temp_data_link = None
        self.setAcceptHoverEvents(True)

    def __repr__(self):
        return "DataSlot (%s.%s %s)" % (self.owner.name, self.name, self.type)

    def updateColor(self):
        if self.hover:
            self.fillColor = self.fillColor_highlight
        elif self.optional:
            self.fillColor = self.fillColor_optional
        elif not self.connected():
            self.fillColor = self.fillColor_not_connected
        else:
            self.fillColor = self.fillColor_regular

    def node(self):
        """The Node that this Slot belongs to is its parent item."""
        return self.parentItem()

    def connectTo(self, target):
        """Convenience method to connect this to another DataSlot.

        This creates an DataLink and directly connects it, in contrast to the mouse
        events that first create an DataLink temporarily and only connect if the
        user releases on a valid target Knob.
        """

        if not isinstance(target, DataSlot):
            print("Ignoring connection to all element types except DataSlot and derived classes.")
            return

        if self.reachedMaxConnections() or target.reachedMaxConnections():
            print("One of the slots can accept no more connections.")
            return

        if target is self:
            print("Can't connect DataSlot to itself.")
            return
            # raise KnobConnectionError(
            #     "Can't connect a Knob to itself.")

        if not ((isinstance(self, InputDataSlot) and isinstance(target, OutputDataSlot)) or (isinstance(self, OutputDataSlot) and isinstance(target, InputDataSlot))):
            print("Only InputDataSlot and OutputDataSlot can be connected.")
            return
            # raise KnobConnectionError(
            #     "Can't connect Knobs of same type.")

        if not self.type == target.type:
            print("Two slots of different value types cannot be connected.")
            return

        new_conn = set([self, target])
        for data_link in self.dataLinks:
            existing_conn = set([data_link.source, data_link.target])
            diff = existing_conn.difference(new_conn)
            if not diff:
                raise KnobConnectionError(
                    "Connection already exists.")

        new_data_link = DataLink()
        new_data_link.source = self
        new_data_link.target = target

        self.addDataConnection(new_data_link)
        target.addDataConnection(new_data_link)

        new_data_link.updatePath()

    def connected(self):
        if len(self.dataLinks):
            return True
        return False

    def scene(self):
        return self.owner.workflow.getScene()

    def addDataConnection(self, data_link):
        """Add the given DataLink to the internal tracking list.

        This is only one part of the Slot connection procedure. It enables us to
        later traverse the whole graph and to see how many connections there
        currently are.

        Also make sure it is added to the QGraphicsScene, if not yet done.
        """
        self.dataLinks.append(data_link)
        scene = self.scene()
        if data_link not in scene.items():
            scene.addItem(data_link)

    def removeDataConnection (self, data_link):
        """Remove th given DataLink from the internal tracking list.

        If it is unknown, do nothing. Also remove it from the QGraphicsScene.
        """
        self.dataLinks.remove(data_link)
        scene = self.scene()
        if data_link in scene.items():
            scene.removeItem(data_link)

    def setUUID(self, uuid):
        self.uuid = uuid

    def boundingRect(self):
        """Return the bounding box of this Knob."""
        rect = QtCore.QRectF(self.x,
                             self.y,
                             self.w,
                             self.h)
        return rect

    def highlight(self, toggle):
        """Toggle the highlight color on/off.

        Store the old color in a new attribute, so it can be restored.
        """
        if toggle:
            self.hover = True
        else:
            self.hover = False
        self.updateColor()

    def paint(self, painter, option, widget):
        """Draw the DataSlot's shape and label."""
        self.updateColor()
        bbox = self.boundingRect()

        # Draw a filled rectangle.
        painter.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        painter.setBrush(QtGui.QBrush(self.fillColor))
        painter.drawRect(bbox)

        # Draw a text label next to it. Position depends on the flow.
        text_size = helpers.getTextSize(self.displayName, painter=painter)

        if self.__class__ == InputDataSlot:
            x = bbox.right() + self.spacing
        else:
            x = bbox.left() - self.spacing - text_size.width()
        y = bbox.bottom()

        painter.setPen(QtGui.QPen(self.labelColor))
        painter.drawText(int(x), int(y), self.displayName)

    def hoverEnterEvent(self, event):
        """Change the Slot's rectangle color."""
        self.highlight(True)
        super(DataSlot, self).hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Change the Slot's rectangle color."""
        self.highlight(False)
        super(DataSlot, self).hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        """Handle DataLink creation."""
        if event.button() == QtCore.Qt.LeftButton:
            if not self.reachedMaxConnections():
                print("Creating new dataLink.")
                self.temp_data_link = DataLink()
                self.temp_data_link.temporary = True
                self.temp_data_link.source = self
                self.temp_data_link.targetPos = event.scenePos()
                self.temp_data_link.updatePath()
                self.addDataConnection(self.temp_data_link)

    def mouseMoveEvent(self, event):
        """Update DataLink position when currently creating one."""
        if self.temp_data_link:
            self.temp_data_link.targetPos = event.scenePos()
            self.temp_data_link.updatePath()

    def mouseReleaseEvent(self, event):
        """Try to create DataLink."""
        if self.temp_data_link:
            print("trying to connect two knobs (block)")
            if event.button() == QtCore.Qt.LeftButton:
                node = self.parentItem()
                scene = node.scene()
                x = event.scenePos().x()
                y = event.scenePos().y()
                qtr = QtGui.QTransform()
                self.temp_data_link.destroy()
                self.temp_data_link = None
                target = scene.itemAt(x, y, qtr)
                if target:
                    self.connectTo(target)
                    return

                print("No target found.")

    def reachedMaxConnections(self):
        if self.maxConnections < 0:
            return False
        number_of_non_temporary_data_links = 0
        for link in self.dataLinks:
            if not link.temporary:
                number_of_non_temporary_data_links += 1
        if number_of_non_temporary_data_links < self.maxConnections:
            return False
        return True

    def finalizeDataLink(self, data_link):
        """This intentionally is a NoOp on the Knob baseclass.

        It is meant for subclass Knobs to implement special behaviour
        that needs to be considered when connecting two Knobs.
        """
        pass
        # TODO

    def destroy(self):
        """Remove this Slot, its DataLinks and associations."""
        print("destroy slot:", self)
        datalink_to_be_deleted = self.dataLinks[::]  # Avoid shrinking during deletion.
        for data_link in datalink_to_be_deleted:
            data_link.destroy()
        # node = self.parentItem()
        # if node:
        #     node.removeSlot(self)

        self.scene().removeItem(self)
        del self

    def addSlotMenuActions(self, menu):
        sub_menu = menu.addMenu("Data slot")

        def _rename():
            temp = QtWidgets.QInputDialog()
            new_name, ok_pressed = QtWidgets.QInputDialog.getText(temp, "Change name of the slot", "New name")
            if ok_pressed:
                self.name = new_name
                self.displayName = self.name
                self.owner.callUpdatePositionOfWholeWorkflow()

        rename_slot_action = sub_menu.addAction("Rename")
        rename_slot_action.triggered.connect(_rename)

        def _delete():
            self.destroy()
            self.owner.callUpdatePositionOfWholeWorkflow()

            # TODO resize block after deletion

        delete_slot_action = sub_menu.addAction("Delete")
        delete_slot_action.triggered.connect(_delete)

        sub_menu_2 = menu.addMenu("Delete dataLink")

        def _delete_data_link(idx):
            print(idx)
            self.dataLinks[idx].destroy()

        data_links = self.dataLinks
        idx = 0
        for data_link in data_links:
            the_other_slot = data_link.giveTheOtherSlot(self)
            if the_other_slot:
                delete_data_link_action = sub_menu_2.addAction("to %s" % the_other_slot.name)
                delete_data_link_action.triggered.connect(lambda checked, idx=idx: _delete_data_link(idx))
            idx += 1

    def contextMenuEvent(self, event):
        temp = QtWidgets.QWidget()
        menu = QtWidgets.QMenu(temp)
        self.addSlotMenuActions(menu)
        menu.exec(QtGui.QCursor.pos())

    def getParentUUID(self):
        if self.parentItem():
            return self.parentItem().uuid
        else:
            return None

    def getDictForJSON(self):
        answer = {'classname': self.__class__.__name__, 'uuid': self.uuid, 'parent_uuid': self.getParentUUID()}
        answer.update({'name': self.name})
        return answer

# def ensureEdgeDirection(data_link):
#     """Make sure the DataLink direction is as described below.
#
#        .source --> .target
#     OutputDataSlot --> InputDataSlot
#
#     Which basically translates to:
#
#     'The Node with the OutputKnob is the child of the Node with the InputKnob.'
#
#     This may seem the exact opposite way as expected, but makes sense
#     when seen as a hierarchy: A Node which output depends on some other
#     Node's input can be seen as a *child* of the other Node. We need
#     that information to build a directed graph.
#
#     We assume here that there always is an InputKnob and an OutputKnob
#     in the given DataLink, just their order may be wrong. Since the
#     serialization relies on that order, it is enforced here.
#     """
#     print("ensure DataLink direction")
#     if isinstance(data_link.target, OutputDataSlot):
#         assert isinstance(data_link.source, InputDataSlot)
#         current_target = data_link.source
#         data_link.source = data_link.target
#         data_link.target = current_target
#     else:
#         assert isinstance(data_link.source, OutputDataSlot)
#         assert isinstance(data_link.target, InputDataSlot)
#
#     print("src:", data_link.source.__class__.__name__,
#           "trg:", data_link.target.__class__.__name__)


class InputDataSlot (DataSlot):
    """
    Class describing input/output parameter of block
    """
    def __init__(self, owner, name, type, optional=False):
        DataSlot.__init__(self, owner, name, type, optional)

    def __repr__(self):
        return "InputDataSlot (%s.%s %s)" % (self.owner.name, self.name, self.type)


class OutputDataSlot (DataSlot):
    """
    Class describing input/output parameter of block
    """
    def __init__ (self, owner, name, type, optional=False):
        DataSlot.__init__(self, owner, name, type, optional)

    def __repr__(self):
        return "OutputDataSlot (%s.%s %s)" % (self.owner.name, self.name, self.type)


class DataLink(QtWidgets.QGraphicsPathItem):
    """
    Represents a connection between source and receiver DataSlots
    """
    def __init__(self, input=None, output=None, **kwargs):
        super(DataLink, self).__init__(**kwargs)
        self.lineColor = QtGui.QColor(0, 0, 250)
        self.removalColor = QtCore.Qt.red
        self.thickness = 2
        self.uuid = str(uuid.uuid4())

        self.source = None  # DataProvider slot
        self.target = None  # DataConsumer slot

        self.sourcePos = QtCore.QPointF(0, 0)
        self.targetPos = QtCore.QPointF(0, 0)

        self.curv1 = 0.6
        self.curv3 = 0.4

        self.curv2 = 0.2
        self.curv4 = 0.8

        self.setAcceptHoverEvents(True)

        self.temporary = False

    def __str__(self):
        return "Datalink (%s -> %s)" % (self.source, self.target)

    def __repr__(self):
        return self.__str__()

    def mousePressEvent(self, event):
        """Delete DataLink if icon is clicked with DELETE_MODIFIER_KEY pressed."""
        left_mouse = event.button() == QtCore.Qt.LeftButton
        mod = event.modifiers() == DELETE_MODIFIER_KEY
        if left_mouse and mod:
            self.destroy()

    def updatePath(self):
        """Adjust current shape based on DataSlots and curvature settings."""
        if self.source:
            self.sourcePos = self.source.mapToScene(
                self.source.boundingRect().center())

        if self.target:
            self.targetPos = self.target.mapToScene(
                self.target.boundingRect().center())

        path = QtGui.QPainterPath()
        path.moveTo(self.sourcePos)

        dx = self.targetPos.x() - self.sourcePos.x()
        dy = self.targetPos.y() - self.sourcePos.y()

        ctrl1 = QtCore.QPointF(self.sourcePos.x() + dx * self.curv1,
                               self.sourcePos.y() + dy * self.curv2)
        ctrl2 = QtCore.QPointF(self.sourcePos.x() + dx * self.curv3,
                               self.sourcePos.y() + dy * self.curv4)
        path.cubicTo(ctrl1, ctrl2, self.targetPos)
        self.setPath(path)

    def paint(self, painter, option, widget):
        """Paint DataLink color depending on modifier key pressed or not."""
        mod = QtWidgets.QApplication.keyboardModifiers() == DELETE_MODIFIER_KEY
        if mod:
            self.setPen(QtGui.QPen(self.removalColor, self.thickness))
        else:
            self.setPen(QtGui.QPen(self.lineColor, self.thickness))

        # self.setBrush(QtCore.Qt.NoBrush)
        self.setZValue(1)
        self.setOpacity(0.5)
        super(DataLink, self).paint(painter, option, widget)

    def destroy(self):
        """Remove this DataLink and its reference in other objects."""
        print("destroy DataLink:", self)
        if self.source:
            self.source.removeDataConnection(self)
        if self.target:
            self.target.removeDataConnection(self)
        del self

    def setVisibleIfSlotsAreVisible(self):
        if self.source.isVisible() and self.target.isVisible():
            self.setVisible(True)
        else:
            self.setVisible(False)

    def giveTheOtherSlot(self, first_slot):
        if self.source == first_slot:
            return self.target
        if self.target == first_slot:
            return self.source
        return None

    def getDictForJSON(self):
        answer = {'classname': self.__class__.__name__, 'uuid': self.uuid}
        answer.update({'ds1_uuid': self.source.uuid, 'ds2_uuid': self.target.uuid})
        return answer

