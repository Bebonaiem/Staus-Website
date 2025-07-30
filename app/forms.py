from flask_wtf import FlaskForm
from wtforms import (StringField, PasswordField, SubmitField, URLField, TextAreaField, 
                     SelectField, DateTimeLocalField, IntegerField, SelectMultipleField)
from wtforms.validators import DataRequired, Email, URL, Optional, NumberRange
from flask_babel import gettext as _l

class LoginForm(FlaskForm):
    email = StringField(_l('Email'), validators=[DataRequired(), Email()])
    password = PasswordField(_l('Password'), validators=[DataRequired()])
    submit = SubmitField(_l('Login'))

class ServiceAddForm(FlaskForm):
    name = StringField(_l('service_name'), validators=[DataRequired()])
    url = URLField(_l('service_url'), validators=[DataRequired(), URL()])
    icon = StringField(_l('Font Awesome Icon'), default='fa-solid fa-globe', validators=[Optional()], description=_l("e.g., fa-solid fa-database, fa-brands fa-aws"))
    submit = SubmitField(_l('add_service'))

class ServiceEditForm(FlaskForm):
    name = StringField(_l('service_name'), validators=[DataRequired()])
    url = URLField(_l('service_url'), validators=[DataRequired(), URL()])
    icon = StringField(_l('Font Awesome Icon'), default='fa-solid fa-globe', validators=[Optional()])
    submit = SubmitField(_l('Save Changes'))

class SettingsForm(FlaskForm):
    page_title = StringField(_l('page_title'), validators=[DataRequired()])
    slack_webhook_url = URLField(_l('slack_webhook_url'), validators=[Optional(), URL()])
    check_interval_seconds = IntegerField(
        _l('Check Interval (seconds)'), 
        validators=[DataRequired(), NumberRange(min=10, max=3600)],
        description=_l("How often to check service status. Min: 10, Max: 3600.")
    )
    submit = SubmitField(_l('save_settings'))

class IncidentForm(FlaskForm):
    title = StringField(_l('Title'), validators=[DataRequired()])
    update_text = TextAreaField(_l('Initial Update'), validators=[DataRequired()])
    status = SelectField(_l('Status'), choices=[('Investigating', 'Investigating'), ('Identified', 'Identified'), ('Monitoring', 'Monitoring'), ('Resolved', 'Resolved')], validators=[DataRequired()])
    severity = SelectField(_l('Severity'), choices=[('notice', 'Notice'), ('warning', 'Warning'), ('critical', 'Critical')], validators=[DataRequired()])
    submit = SubmitField(_l('Report Incident'))

class IncidentUpdateForm(FlaskForm):
    update_text = TextAreaField(_l('Update Message'), validators=[DataRequired()])
    status = SelectField(_l('New Status'), choices=[('Investigating', 'Investigating'), ('Identified', 'Identified'), ('Monitoring', 'Monitoring'), ('Resolved', 'Resolved')], validators=[DataRequired()])
    submit = SubmitField(_l('Post Update'))

class MaintenanceForm(FlaskForm):
    title = StringField(_l('Title'), validators=[DataRequired()])
    description = TextAreaField(_l('Description'), validators=[DataRequired()])
    start_time = DateTimeLocalField(_l('Start Time'), format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    end_time = DateTimeLocalField(_l('End Time'), format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    
    # Field to select affected services, populated dynamically in the route
    affected_services = SelectMultipleField(
        _l('Affected Services'), 
        coerce=int, # Converts form submission values to integers
        validators=[DataRequired()],
        description=_l("Select all services that will be affected by this maintenance.")
    )

    submit = SubmitField(_l('Schedule Maintenance'))