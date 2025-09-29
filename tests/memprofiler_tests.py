import sys
import os
from io import BytesIO

import unittest

from rdbtools import RdbParser
from rdbtools import MemoryCallback


from rdbtools.memprofiler import MemoryRecord, PrintAllKeys, GroupedPrintAllKeys

CSV_WITH_EXPIRY = """database,type,key,size_in_bytes,encoding,num_elements,len_largest_element,expiry
0,string,expires_ms_precision,128,string,27,27,2022-12-25T10:11:12.573000
"""

CSV_WITHOUT_EXPIRY = """database,type,key,size_in_bytes,encoding,num_elements,len_largest_element,expiry
0,list,ziplist_compresses_easily,301,quicklist,6,36,
"""

CSV_WITH_MODULE = """database,type,key,size_in_bytes,encoding,num_elements,len_largest_element,expiry
0,string,simplekey,72,string,7,7,
0,module,foo,101,ReJSON-RL,1,101,
"""

class Stats(object):
    def __init__(self):
        self.sums = {}
        self.records = {}

    def next_record(self, record):
        if record.type not in self.sums:
            self.sums[record.type] = 0
        self.sums[record.type] += record.bytes
        if record.key is not None:
            self.records[record.key] = record


def get_stats(file_name):
    stats = Stats()
    callback = MemoryCallback(stats, 64)
    parser = RdbParser(callback)
    parser.parse(os.path.join(os.path.dirname(__file__), 'dumps', file_name))
    return stats.records

def get_sums(file_name):
    stats = Stats()
    callback = MemoryCallback(stats, 64)
    parser = RdbParser(callback)
    parser.parse(os.path.join(os.path.dirname(__file__), 'dumps', file_name))
    return stats.sums

def get_csv(dump_file_name, prefix_map=None, auto_group=False):
    buff = BytesIO()
    if prefix_map or auto_group:
        mapped = list(prefix_map.items()) if prefix_map else None
        stream = GroupedPrintAllKeys(buff, None, None, mapped, auto_detect=auto_group)
    else:
        stream = PrintAllKeys(buff, None, None)
    callback = MemoryCallback(stream, 64)
    parser = RdbParser(callback)
    parser.parse(os.path.join(os.path.dirname(__file__), 
                    'dumps', dump_file_name))
    csv = buff.getvalue().decode()
    return csv

class MemoryCallbackTestCase(unittest.TestCase):
    def setUp(self):
        pass

    def test_csv_with_expiry(self):
        csv = get_csv('keys_with_expiry.rdb')
        self.assertEquals(csv, CSV_WITH_EXPIRY)

    def test_csv_without_expiry(self):
        csv = get_csv('ziplist_that_compresses_easily.rdb')
        self.assertEquals(csv, CSV_WITHOUT_EXPIRY)

    def test_csv_with_module(self):
        csv = get_csv('redis_40_with_module.rdb')
        self.assertEquals(csv, CSV_WITH_MODULE)

    def test_grouped_csv(self):
        csv = get_csv('parser_filters.rdb', auto_group=True)
        lines = csv.strip().split('\n')
        self.assertEqual(lines[0], "database,type,key,size_in_bytes,encoding,num_elements,len_largest_element,expiry")
        prefix_rows = {
            row.split(',')[2]: row.split(',')
            for row in lines[1:]
            if row.split(',')[2].endswith(':*')
        }
        self.assertIn('l:*', prefix_rows)
        lists = prefix_rows['l:*']
        self.assertEqual(lists[0], '0')
        self.assertEqual(lists[1], 'list')
        self.assertEqual(int(lists[3]), 2464)
        self.assertEqual(lists[4], 'quicklist')
        self.assertEqual(int(lists[5]), 33)
        self.assertEqual(int(lists[6]), 578)

    def test_grouped_csv_manual_alias(self):
        csv = get_csv('parser_filters.rdb', prefix_map={'l': 'lists'})
        lines = csv.strip().split('\n')
        grouped = [line for line in lines[1:] if ',lists,' in line]
        self.assertEqual(len(grouped), 1)
        cols = grouped[0].split(',')
        self.assertEqual(cols[0], '0')
        self.assertEqual(cols[1], 'list')
        self.assertEqual(cols[2], 'lists')
        self.assertEqual(int(cols[3]), 2464)
        self.assertEqual(cols[4], 'quicklist')
        self.assertEqual(int(cols[5]), 33)
        self.assertEqual(int(cols[6]), 578)

    def test_expiry(self):
        stats = get_stats('keys_with_expiry.rdb')

        expiry = stats['expires_ms_precision'].expiry
        self.assertEquals(expiry.year, 2022)
        self.assertEquals(expiry.month, 12)
        self.assertEquals(expiry.day, 25)
        self.assertEquals(expiry.hour, 10)
        self.assertEquals(expiry.minute, 11)
        self.assertEquals(expiry.second, 12)
        self.assertEquals(expiry.microsecond, 573000)        

    def test_len_largest_element(self):
        stats = get_stats('ziplist_that_compresses_easily.rdb')

        self.assertEqual(stats['ziplist_compresses_easily'].len_largest_element, 36, "Length of largest element does not match")

    def test_rdb_with_module(self):
        stats = get_stats('redis_40_with_module.rdb')

        self.assertTrue('simplekey' in stats)
        self.assertTrue('foo' in stats)
        expected_record = MemoryRecord(database=0, type='module', key='foo',
                                       bytes=101, encoding='ReJSON-RL', size=1,
                                       len_largest_element=101, expiry=None)
        self.assertEquals(stats['foo'], expected_record)

    def test_rdb_with_module_aux(self):
        sums = get_sums('redis_60_with_module_aux.rdb')
        self.assertEquals(sums['module'], 32)

    def test_rdb_with_stream(self):
        stats = get_stats('redis_50_with_streams.rdb')

        self.assertTrue('mystream' in stats)
        expected_record = MemoryRecord(database=0, type='stream', key='mystream',
                                       bytes=1976, encoding='listpack', size=1,
                                       len_largest_element=184, expiry=None)
        self.assertEquals(stats['mystream'], expected_record)
