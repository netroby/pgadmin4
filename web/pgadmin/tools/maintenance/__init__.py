##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2016, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""A blueprint module implementing the maintenance tool for vacuum"""

import cgi
import json

from flask import url_for, Response, render_template, request, current_app
from flask.ext.babel import gettext as _
from flask.ext.security import login_required

from config import PG_DEFAULT_DRIVER
from pgadmin.misc.bgprocess.processes import BatchProcess, IProcessDesc
from pgadmin.model import Server
from pgadmin.utils import PgAdminModule
from pgadmin.utils.ajax import bad_request, make_json_response
from pgadmin.utils.driver import get_driver

MODULE_NAME = 'maintenance'


class MaintenanceModule(PgAdminModule):
    """
    class MaintenanceModule(PgAdminModule)

        A module class for maintenance tools of vacuum which is derived from
        PgAdminModule.

    Methods:
    -------
    * get_own_javascripts()
      - Method is used to load the required javascript files for maintenance
        tool module
    * get_own_stylesheets()
      - Returns the list of CSS file used by Maintenance module
    """
    LABEL = _('Maintenance')

    def get_own_javascripts(self):
        scripts = list()
        for name, script in [
                ['pgadmin.tools.maintenance', 'js/maintenance']
                ]:
            scripts.append({
                'name': name,
                'path': url_for('maintenance.index') + script,
                'when': None
                })

        return scripts

    def get_own_stylesheets(self):
        """
        Returns:
            list: the stylesheets used by this module.
        """
        stylesheets = [
            url_for('maintenance.static', filename='css/maintenance.css')
            ]
        return stylesheets

blueprint = MaintenanceModule(MODULE_NAME, __name__)


class Message(IProcessDesc):

    def __init__(self, _sid, _data, _query):
        self.sid = _sid
        self.data = _data
        self.query = _query

    @property
    def message(self):
        res = _("Maintenance ({0})")

        if self.data['op'] == "VACUUM":
            return res.format(_('Vacuum'))
        if self.data['op'] == "ANALYZE":
            return res.format(_('Analyze'))
        if self.data['op'] == "REINDEX":
            return res.format(_('Reindex'))
        if self.data['op'] == "CLUSTER":
            return res.format(_('Cluster'))

    def details(self, cmd, args):

        res = None

        if self.data['op'] == "VACUUM":
            res = _('VACUUM ({0})')

            opts = []
            if self.data['vacuum_full']:
                opts.append(_('FULL'))
            if self.data['vacuum_freeze']:
                opts.append(_('FREEZE'))
            if self.data['verbose']:
                opts.append(_('VERBOSE'))

            res = res.format(', '.join(str(x) for x in opts))

        if self.data['op'] == "ANALYZE":
            res = _('ANALYZE')
            if self.data['verbose']:
                res += '(' + _('VERBOSE') + ')'

        if self.data['op'] == "REINDEX":
            if 'schema' in self.data and self.data['schema']:
                return _('REINDEX TABLE')
            res = _('REINDEX')

        if self.data['op'] == "CLUSTER":
            res = _('CLUSTER')

        res = '<div class="h5">' + cgi.escape(res).encode(
            'ascii', 'xmlcharrefreplace'
        )

        res += '</div><div class="h5">'
        res += cgi.escape(
            _("Running Query:")
        ).encode('ascii', 'xmlcharrefreplace')
        res += '</b><br><i>'
        res += cgi.escape(self.query).encode('ascii', 'xmlcharrefreplace')
        res += '</i></div>'

        return res


@blueprint.route("/")
@login_required
def index():
    return bad_request(
        errormsg=_("This URL can not be called directly!")
    )


@blueprint.route("/js/maintenance.js")
@login_required
def script():
    """render the maintenance tool of vacuum javascript file"""
    return Response(
        response=render_template("maintenance/js/maintenance.js",  _=_),
        status=200,
        mimetype="application/javascript"
    )


@blueprint.route('/create_job/<int:sid>/<int:did>', methods=['POST'])
@login_required
def create_maintenance_job(sid, did):
    """
    Args:
        sid: Server ID
        did: Database ID

        Creates a new job for maintenance vacuum operation

    Returns:
        None
    """
    if request.form:
        # Convert ImmutableDict to dict
        data = dict(request.form)
        data = json.loads(data['data'][0])
    else:
        data = json.loads(request.data.decode())

    # Fetch the server details like hostname, port, roles etc
    server = Server.query.filter_by(
        id=sid).first()

    if server is None:
        return make_json_response(
            success=0,
            errormsg=_("Couldn't find the given server")
        )

    # To fetch MetaData for the server
    driver = get_driver(PG_DEFAULT_DRIVER)
    manager = driver.connection_manager(server.id)
    conn = manager.connection()
    connected = conn.connected()

    if not connected:
        return make_json_response(
            success=0,
            errormsg=_("Please connect to the server first...")
        )

    utility = manager.utility('sql')

    # Create the command for the vacuum operation
    query = render_template(
        'maintenance/sql/command.sql', conn=conn, data=data
    )

    args = [
        '--host', server.host, '--port', str(server.port),
        '--username', server.username, '--dbname',
        driver.qtIdent(conn, data['database']),
        '--command', query
    ]

    try:
        p = BatchProcess(
            desc=Message(sid, data, query),
            cmd=utility, args=args
        )
        manager.export_password_env(p.id)
        p.start()
        jid = p.id
    except Exception as e:
        current_app.logger.exception(e)
        return make_json_response(
            status=410,
            success=0,
            errormsg=str(e)
        )

    # Return response
    return make_json_response(
        data={'job_id': jid, 'status': True, 'info': 'Maintenance job created'}
    )
