# -*- coding: utf-8 -*-

from mamonsu.plugins.pgsql.plugin import PgsqlPlugin as Plugin
from .pool import Pooler
import time
import sys
from mamonsu.lib.zbx_template import ZbxTemplate


class PgHealth(Plugin):
    AgentPluginType = 'pg'
    DEFAULT_CONFIG = {'uptime': str(60 * 10), 'cache': str(80)}
    query_health = "select 1 as health;"
    query_uptime = "select ceil(extract(epoch from pg_postmaster_start_time()));"
    key_ping = "pgsql.ping{0}"
    key_uptime = "pgsql.uptime{0}"
    key_cache = "pgsql.cache{0}"

    def run(self, zbx):

        start_time = time.time()
        Pooler.query(self.query_health)
        zbx.send(self.key_ping.format('[]'), (time.time() - start_time) * 1000)
        result = Pooler.query(self.query_uptime)
        zbx.send(self.key_uptime.format('[]'), int(result[0][0]))

    def items(self, template, dashboard=False):
        result = ''
        if self.Type == "mamonsu":
            delay = self.plugin_config('interval')
            value_type = Plugin.VALUE_TYPE.numeric_unsigned
        else:
            delay = 5  # TODO check delay
            value_type = Plugin.VALUE_TYPE.numeric_float
        result += template.item({
            'name': 'PostgreSQL: ping',
            'key': self.right_type(self.key_ping),
            'value_type': Plugin.VALUE_TYPE.numeric_float,
            'units': Plugin.UNITS.ms,
            'delay': delay
        }) + template.item({
            'name': 'PostgreSQL: cache hit ratio',
            'key': self.right_type(self.key_cache, "hit"),
            'value_type': value_type,
            'units': Plugin.UNITS.percent,
            'type': Plugin.TYPE.CALCULATED,
            'params': "last(//pgsql.blocks[hit])*100/(last(//pgsql.blocks[hit])+last(//pgsql.blocks[read]))"
        }) + template.item({
            'name': 'PostgreSQL: service uptime',
            'key': self.right_type(self.key_uptime),
            'value_type': value_type,
            'delay': self.plugin_config('interval'),
            'units': Plugin.UNITS.unixtime
        })
        if not dashboard:
            return result
        else:
            return [{'dashboard': {'name': self.right_type(self.key_ping),
                                   'page': ZbxTemplate.dashboard_page_instance['name'],
                                   'size': ZbxTemplate.dashboard_widget_size_medium,
                                   'position': 1}},
                    {'dashboard': {'name': self.right_type(self.key_uptime),
                                   'page': ZbxTemplate.dashboard_page_instance['name'],
                                   'size': ZbxTemplate.dashboard_widget_size_medium,
                                   'position': 2}},
                    {'dashboard': {'name': self.right_type(self.key_cache, 'hit'),
                                   'page': ZbxTemplate.dashboard_page_instance['name'],
                                   'size': ZbxTemplate.dashboard_widget_size_medium,
                                   'position': 3}}]

    def triggers(self, template, dashboard=False):
        result = template.trigger({
            'name': 'PostgreSQL service was restarted on '
                    '{HOSTNAME} (uptime={ITEM.LASTVALUE})',
            'expression': '{#TEMPLATE:' + self.right_type(self.key_uptime) + '.last()}&lt;' +
                          str(self.plugin_config('uptime'))
        }) + template.trigger({
            'name': 'PostgreSQL cache hit ratio too low on '
                    '{HOSTNAME} ({ITEM.LASTVALUE})',
            'expression': '{#TEMPLATE:' + self.right_type(self.key_cache, "hit") + '.last()}&lt;' +
                          str(self.plugin_config('cache'))
        }) + template.trigger({
            'name': 'PostgreSQL no ping from PostgreSQL for 3 minutes '
                    '{HOSTNAME} ',
            'expression': '{#TEMPLATE:' + self.right_type(self.key_ping) + '.nodata(180)}=1'
        })
        return result

    def keys_and_queries(self, template_zabbix):
        result = ['{0}[*],$2 $1 -c "{1}"'.format(self.key_ping.format(''), self.query_health),
                  '{0}[*],$2 $1 -c "{1}"'.format(self.key_uptime.format(''), self.query_uptime)]
        return template_zabbix.key_and_query(result)
