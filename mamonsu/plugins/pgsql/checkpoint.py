# -*- coding: utf-8 -*-

from mamonsu.plugins.pgsql.plugin import PgsqlPlugin as Plugin
from .pool import Pooler
from mamonsu.lib.zbx_template import ZbxTemplate


class Checkpoint(Plugin):
    AgentPluginType = 'pg'
    Interval = 60 * 5

    query = "select {0} from pg_catalog.pg_stat_bgwriter; "  # for mamonsu and agent
    query_interval = "select {0}*3600 from pg_catalog.pg_stat_bgwriter; "  # for mamonsu and agent checkpoints in hour
    key = 'pgsql.checkpoint{0}'

    DEFAULT_CONFIG = {'max_checkpoint_by_wal_in_hour': str(12)}

    Items = [
        # key, zbx_key, description,
        #    ('graph name', color, side), units, delta, factor

        ('checkpoints_timed', 'count_timed',
            'checkpoints: by timeout (in hour)',
            ('PostgreSQL checkpoint', '00CC00', 0),
            Plugin.UNITS.none, Plugin.DELTA.speed_per_second, 60 * 60),

        ('checkpoints_req', 'count_wal',
            'checkpoints: by wal (in hour)',
            ('PostgreSQL checkpoint', 'CC0000', 0),
            Plugin.UNITS.none, Plugin.DELTA.speed_per_second, 60 * 60),

        ('checkpoint_write_time', 'write_time',
            'checkpoint: write time',
            ('PostgreSQL checkpoints', '0000CC', 1),
            Plugin.UNITS.ms, Plugin.DELTA.speed_per_second, 1),

        ('checkpoint_sync_time', 'checkpoint_sync_time',
            'checkpoint: sync time',
            ('PostgreSQL checkpoints', '000000', 1),
            Plugin.UNITS.ms, Plugin.DELTA.speed_per_second, 1)
    ]

    def run(self, zbx):
        params = [x[0] for x in self.Items]
        result = Pooler.query(
            self.query.format(
                ', '.join(params)))
        for idx, val in enumerate(result[0]):
            key, val = 'pgsql.checkpoint[{0}]'.format(
                self.Items[idx][1]), int(val)
            zbx.send(key, val * self.Items[idx][6], self.Items[idx][5])
        del params, result

    def items(self, template, dashboard=False):
        result = ''
        if self.Type == "mamonsu":
            delta = Plugin.DELTA.as_is
        else:
            delta = Plugin.DELTA.speed_per_second
        for item in self.Items:
            result += template.item({
                'key': self.right_type(self.key, item[1]),
                'name': 'PostgreSQL {0}'.format(item[2]),
                'value_type': Plugin.VALUE_TYPE.numeric_float,
                'units': item[4],
                'delay': self.plugin_config('interval'),
                'delta': delta
            })
        if not dashboard:
            return result
        else:
            return []

    def graphs(self, template, dashboard=False):
        items_checkpoints, items_checkpoints_write_sync = [], []
        for item in self.Items:
            if item[3][2] == 0:
                items_checkpoints.append({
                    'key': self.right_type(self.key, item[1]),
                    'color': item[3][1],
                    'delay': self.Interval
                })
            if item[3][2] == 1:
                items_checkpoints_write_sync.append({
                    'key': self.right_type(self.key, item[1]),
                    'color': item[3][1],
                    'delay': self.Interval
                })
        result = template.graph({'name': 'PostgreSQL checkpoints count', 'items': items_checkpoints}) + \
                 template.graph({'name': 'PostgreSQL checkpoints write/sync', 'items': items_checkpoints_write_sync})
        if not dashboard:
            return result
        else:
            return [{'dashboard': {'name': 'PostgreSQL checkpoints count',
                                   'page': ZbxTemplate.dashboard_page_overview['name'],
                                   'size': ZbxTemplate.dashboard_widget_size_medium,
                                   'position': 9}},
                    {'dashboard': {'name': 'PostgreSQL checkpoints write/sync',
                                   'page': ZbxTemplate.dashboard_page_overview['name'],
                                   'size': ZbxTemplate.dashboard_widget_size_medium,
                                   'position': 10}}
                    ]

    def triggers(self, template, dashboard=False):
        return template.trigger({
            'name': 'PostgreSQL required checkpoints occurs to '
            'frequently on {HOSTNAME}',
            'expression': '{#TEMPLATE:' + self.right_type(self.key, self.Items[1][1]) +
            '.last()}&gt;' + self.plugin_config(
                'max_checkpoint_by_wal_in_hour')
        })

    def keys_and_queries(self, template_zabbix):
        result = []
        for num, item in enumerate(self.Items):
            if num > 1:
                result.append(
                    '{0}[*],$2 $1 -c "{1}"'.format(self.key.format("." + item[1]), self.query.format(item[0])))
            else:
                result.append(
                    '{0}[*],$2 $1 -c "{1}"'.format(self.key.format("." + item[1]), self.query_interval.format(item[0])))
        return template_zabbix.key_and_query(result)
