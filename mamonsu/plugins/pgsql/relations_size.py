# -*- coding: utf-8 -*-

from mamonsu.plugins.pgsql.plugin import PgsqlPlugin as Plugin
from .pool import Pooler
from mamonsu.lib.plugin import PluginDisableException


class RelationsSize(Plugin):
    DEFAULT_CONFIG = {'enabled': 'False'}
    key_rel_size_discovery = "pgsql.relation.size{0}"

    def __init__(self, config):
        super(Plugin, self).__init__(config)
        if self.is_enabled():
            self.relations = None
            self.query_template = """SELECT relation.schema
             , relation.name
             , CASE WHEN l.mode = 'AccessExclusiveLock' THEN '-1'
                   ELSE (pg_total_relation_size(cl.oid))
               END AS pg_total_relation_size
             , CASE WHEN l.mode = 'AccessExclusiveLock' THEN '-1'
                   ELSE (sum(pg_total_relation_size(inh.inhrelid)))
               END AS pg_total_relation_size_part
        FROM (VALUES {values}) as relation (schema,name)
        LEFT JOIN pg_catalog.pg_class cl ON cl.relname =  relation.name
        LEFT JOIN pg_catalog.pg_namespace ns ON ns.oid = cl.relnamespace AND ns.nspname=relation.schema
        LEFT JOIN pg_catalog.pg_inherits inh ON inh.inhparent = cl.oid
        LEFT JOIN pg_catalog.pg_locks l ON l.relation = cl.oid AND l.mode= 'AccessExclusiveLock' AND l.locktype = 'relation'
        LEFT JOIN pg_catalog.pg_locks l_part ON l_part.relation = inh.inhrelid AND l.mode= 'AccessExclusiveLock' AND l.locktype = 'relation'
        GROUP BY relation.schema
               , relation.name
               , l.mode
               , cl.oid"""

    def create_relations(self):
        config_relations = self._plugin_config.get('relations', None)
        if config_relations is None or config_relations == '':
            self.disable()
            raise PluginDisableException(
                """Disable plugin and exit, because the parameter 'relations' in section [relationssize] is not set. Set this parameter like relations=pg_catalog.pg_class,pg_catalog.pg_user to count size if needed and restart.""")

        self.relations = []
        for relation in config_relations.split(','):
            tmp_rel = relation.split('.')
            if len(tmp_rel) == 3:
                self.relations.append([tmp_rel[0].strip(), tmp_rel[1].strip(), tmp_rel[2].strip()])
            else:
                self.log.error(
                    'The relation "{relation}" is not correct. You need to specify "database_name.schema.table" in the configuration file for mamonsu. Section: [relationssize], parameter: relations '.format(
                        relation=relation))

    def run(self, zbx):
        if not self.relations:
            self.create_relations()
        rels = []
        all_databases = Pooler.databases()
        for database_name, schema, relation in self.relations:
            rels.append({'{#RELATIONNAME}': database_name + '.' + schema + '.' + relation})
            if not (database_name in all_databases):
                self.log.error(
                    '''The database: "{database_name}" do not exists. '''
                    '''Check the the parameter "relations" in section [relatonssize].'''.format(
                        database_name=database_name))
            else:
                result = Pooler.query(query=self.query_template.format(
                    values="('{schema}','{relation}')".format(schema=schema, relation=relation)), db=database_name)
                for schema, name, pg_total_relation_size, pg_total_relation_size_part in result:
                    full_name_relation = database_name + '.' + schema + '.' + relation

                    if pg_total_relation_size is None and pg_total_relation_size_part is None:
                        self.log.error('The relation: "{full_name_relation}" in not correct'.format(
                            full_name_relation=full_name_relation))
                        size = -1
                    elif pg_total_relation_size == -1 or pg_total_relation_size_part == -1:
                        self.log.error(
                            "The relation: {full_name_relation} is locked. "
                            "You can find this lock in query: "
                            "SELECT relation::regclass AS lock_relation, mode FROM  pg_locks "
                            "WHERE relation::regclass = 'pg_locks'::regclass;".format(
                                full_name_relation=full_name_relation))
                        size = -1
                    else:
                        size = (pg_total_relation_size or 0) + (pg_total_relation_size_part or 0)

                    zbx.send('pgsql.relation.size[{0}]'.format(full_name_relation), int(size))

        zbx.send('pgsql.relation.size[]', zbx.json({'data': rels}))

    def discovery_rules(self, template, dashboard=False):
        rule = {
            'name': 'Relation size discovery',
            'key': self.key_rel_size_discovery.format('[{0}]'.format(self.Macros[self.Type])),
        }
        if Plugin.old_zabbix:
            conditions = []
            rule['filter'] = '{#RELATIONNAME}:.*'
        else:
            conditions = [
                {
                    'condition': [
                        {'macro': '{#RELATIONNAME}',
                         'value': '.*',
                         'operator': 8,
                         'formulaid': 'A'}
                    ]
                }
            ]
        items = [
            {'key': self.right_type(self.key_rel_size_discovery, var_discovery="{#RELATIONNAME},"),
             'name': 'Relation size: {#RELATIONNAME}',
             'units': Plugin.UNITS.bytes,
             'value_type': Plugin.VALUE_TYPE.numeric_unsigned,
             'delay': self.plugin_config('interval')},
        ]
        graphs = [
            {
                'name': 'PostgreSQL relation size: {#RELATIONNAME}',
                'type': 1,
                'items': [
                    {'color': '00CC00',
                     'key': self.right_type(self.key_rel_size_discovery, var_discovery="{#RELATIONNAME},")}]
            },
        ]
        return template.discovery_rule(rule=rule, conditions=conditions, items=items, graphs=graphs)
