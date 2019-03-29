import logging

from sqlalchemy import Column, String, ForeignKey, UniqueConstraint, Boolean, event
from sqlalchemy.orm import relationship
from sqlalchemy_utils import UUIDType, JSONType
from marshmallow import fields, EXCLUDE
from marshmallow_sqlalchemy import field_for

from flask import current_app

from common.workflow_types import ParameterVariant

from api_gateway.executiondb.schemas import ExecutionElementBaseSchema
from api_gateway.executiondb.global_variable import GlobalVariable
from api_gateway.executiondb.condition import ConditionSchema
from api_gateway.executiondb.transform import TransformSchema
from api_gateway.executiondb.trigger import TriggerSchema
from api_gateway.executiondb.branch import BranchSchema
from api_gateway.executiondb.workflow_variable import WorkflowVariableSchema
from api_gateway.executiondb import Execution_Base
from api_gateway.executiondb.action import Action, ActionSchema
from api_gateway.executiondb.executionelement import ExecutionElement

logger = logging.getLogger(__name__)


class Workflow(ExecutionElement, Execution_Base):
    __tablename__ = "workflow"
    # playbook_id = Column(UUIDType(binary=False), ForeignKey('playbook.id_', ondelete='CASCADE'))
    name = Column(String(80), nullable=False)
    start = Column(UUIDType(binary=False))
    actions = relationship("Action", cascade="all, delete-orphan", passive_deletes=True)
    branches = relationship("Branch", cascade="all, delete-orphan", passive_deletes=True)
    conditions = relationship("Condition", cascade="all, delete-orphan", passive_deletes=True)
    transforms = relationship("Transform", cascade="all, delete-orphan", passive_deletes=True)
    triggers = relationship("Trigger", cascade="all, delete-orphan", passive_deletes=True)
    is_valid = Column(Boolean, default=False)
    tags = Column(JSONType)
    description = Column(String())
    children = ("actions", "branches", "conditions", "transforms", "triggers")
    workflow_variables = relationship("WorkflowVariable", cascade="all, delete-orphan", passive_deletes=True)

    # __table_args__ = (UniqueConstraint("playbook_id", "name", name="_playbook_workflow"),)

    def __init__(self, name, start=None, id_=None, actions=None, branches=None, conditions=None, transforms=None,
                 triggers=None, workflow_variables=None, is_valid=False, errors=None, tags=None, description=None):
        """Initializes a Workflow object. A Workflow falls under a Playbook, and has many associated Actions
            within it that get executed.

        Args:
            name (str): The name of the Workflow object.
            start (int): ID of the starting Action.
            id_ (str|UUID, optional): Optional UUID to pass into the Action. Must be UUID object or valid UUID string.
                Defaults to None.
            actions (list[Action]): Optional Action objects. Defaults to None.
            branches (list[Branch], optional): A list of Branch objects for the Workflow object. Defaults to None.
            workflow_variables (list[EnvironmentVariable], optional): A list of environment variables for the
                Workflow. Defaults to None.
        """
        ExecutionElement.__init__(self, id_, errors)
        self.name = name
        self.actions = actions if actions else []
        self.branches = branches if branches else []
        self.conditions = conditions if conditions else []
        self.transforms = transforms if transforms else []
        self.triggers = triggers if triggers else []
        self.tags = tags if tags else []
        self.workflow_variables = workflow_variables if workflow_variables else []

        self.start = start
        self.is_valid = is_valid

        self.description = description

        if not self.is_valid:
            self.validate()

    def validate(self):
        """Validates the object"""
        node_ids = [action.id_ for action in self.actions] + \
                   [conditions.id_ for conditions in self.conditions] + \
                   [transforms.id_ for transforms in self.transforms]

        work_var_ids = [workflow_var.id_ for workflow_var in self.workflow_variables]
        global_ids = current_app.running_context.execution_db.session.query(GlobalVariable.id_).all()

        params = [param for action in [action.parameters for action in self.actions] for param in action]

        errors = []
        if not self.start and self.actions:
            errors.append("Workflows must have a starting action.")
        elif self.actions and self.start not in node_ids:
            errors.append(f"Workflow start ID {self.start} not found in nodes")
        for branch in self.branches:
            if branch.source_id not in node_ids:
                errors.append(f"Branch source ID {branch.source_id} not found in nodes")
            if branch.destination_id not in node_ids:
                errors.append(f"Branch destination ID {branch.destination_id} not found in nodes")
        for param in params:
            if param.variant != ParameterVariant.STATIC_VALUE.name:
                if param.value not in node_ids and param.value not in work_var_ids and param.value not in global_ids:
                    errors.append(f"Parameter {param.name} refers to {param.value} not found in {param.variant}.")
        self.errors = errors
        self.is_valid = self._is_valid


@event.listens_for(Workflow, "before_update")
def validate_before_update(mapper, connection, target):
    target.validate()


class WorkflowSchema(ExecutionElementBaseSchema):
    """Schema for workflows
    """
    name = field_for(Workflow, 'name', required=True)
    start = field_for(Workflow, 'start')
    actions = fields.Nested(ActionSchema, many=True)
    branches = fields.Nested(BranchSchema, many=True)
    conditions = fields.Nested(ConditionSchema, many=True)
    transforms = fields.Nested(TransformSchema, many=True)
    triggers = fields.Nested(TriggerSchema, many=True)
    workflow_variables = fields.Nested(WorkflowVariableSchema, many=True)
    tags = fields.Raw()
    description = field_for(Workflow, 'description')

    # TODO: determine if this is needed
    # exclude = ("is_valid",)
    # is_valid = field_for(Workflow, 'is_valid')

    class Meta:
        model = Workflow
        unknown = EXCLUDE
