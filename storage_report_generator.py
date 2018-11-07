#!/usr/bin/env python2
# -*- coding: utf-8 -*-
#
# Copyright 2018 Gabriele Iannetti <g.iannetti@gsi.de>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#


import ConfigParser
import datetime
import argparse
import logging
import sys
import os

import dataset.lustre_dataset_handler as ds
import filter.group_filter_handler as gf
from lfs.disk_usage_info import lustre_total_size

from chart.quota_pct_bar_chart import QuotaPctBarChart
from chart.usage_quota_bar_chart import UsageQuotaBarChart
from chart.usage_pie_chart import UsagePieChart


def check_matplotlib_version():

    import matplotlib

    mplot_ver = matplotlib.__version__

    logging.debug("Running with matplotlib version: %s" % mplot_ver)

    major_version = int(mplot_ver.split('.')[0])

    # Version of matplotlib could be extended by 3 etc., if tested!
    if major_version != 2:
        raise RuntimeError("Supported major matplotlib version should be 2!")


def purge_old_report_files(report_dir):

    pattern = ".svg"

    if not os.path.isdir(report_dir):
        raise RuntimeError("Directory does not exist under: %s" % report_dir)

    file_list = os.listdir(report_dir)

    for filename in file_list:

        if pattern in filename:

            file_path = os.path.join(report_dir, filename)

            logging.debug("Removed old report file: %s" % file_path)

            os.remove(file_path)


def calc_prev_month_datetime():

    now = datetime.datetime.now()
    first = now.replace(day=1)
    prev_month = first - datetime.timedelta(days=1)
    return prev_month


def create_chart_path(chart_dir, chart_filename, time_point):

    chart_filename = chart_filename.replace('{TIME_FORMAT}', time_point)

    return chart_dir + os.path.sep + chart_filename


def create_usage_pie_chart(title, file_path,
                           group_info_list, storage_total_size):

    chart = UsagePieChart(title=title,
                          file_path=file_path,
                          dataset=group_info_list,
                          storage_total_size=storage_total_size)

    chart.create()


def create_quota_pct_bar_chart(title, file_path, group_info_list):

    chart = QuotaPctBarChart(title=title,
                             sub_title='Procedural Usage per Group',
                             file_path=file_path,
                             dataset=group_info_list)

    chart.create()


def create_usage_quota_bar_chart(title, file_path, group_info_list):

    chart = UsageQuotaBarChart(
        title=title,
        file_path=file_path,
        dataset=group_info_list)

    chart.create()


def create_weekly_reports(local, chart_dir, long_name, time_point, config):

    reports_path_list = list()

    #TODO: Extract where the data comes from!!!
    group_info_list = None
    storage_total_size = 0

    if local:

        logging.debug('Weekly Run Mode: LOCAL/DEV')

        group_info_list = ds.create_dummy_group_info_list()
        storage_total_size = 18458963071860736

    else:

        logging.debug('Weekly Run Mode: PRODUCTIVE')

        ds.CONFIG = config

        group_info_list = \
            gf.filter_group_info_items(
                ds.get_group_info_list(
                    gf.filter_system_groups(ds.get_group_names())))

        storage_total_size = \
            lustre_total_size(config.get('storage', 'filesystem'))

    purge_old_report_files(chart_dir)

    # QUOTA-PCT-BAR-CHART
    title = "Group Quota Usage on %s" % long_name

    chart_path = create_chart_path(
        chart_dir,
        config.get('quota_pct_bar_chart', 'filename'),
        time_point)

    create_quota_pct_bar_chart(title, chart_path, group_info_list)

    reports_path_list.append(chart_path)

    # USAGE-QUOTA-BAR-CHART
    title = "Quota and Disk Space Usage on %s" % long_name

    chart_path = create_chart_path(
        chart_dir,
        config.get('usage_quota_bar_chart', 'filename'),
        time_point)

    create_usage_quota_bar_chart(title, chart_path, group_info_list)

    reports_path_list.append(chart_path)

    # USAGE-PIE-CHART
    title = "Storage Usage on %s" % long_name

    chart_path = create_chart_path(
        chart_dir,
        config.get('usage_pie_chart', 'filename'),
        time_point)

    create_usage_pie_chart(title, chart_path, group_info_list,
                           storage_total_size)

    reports_path_list.append(chart_path)

    return reports_path_list


def create_monthly_reports():

    reports_path_list = list()

    return reports_path_list


def transfer_reports(run_mode, prev_month, config, reports_path_list):

    import subprocess

    logging.debug('Transferring Reports')

    if not reports_path_list:
        raise RuntimeError('Input reports path list is not set!')

    remote_protocol = config.get('transfer', 'protocol')
    remote_host = config.get('transfer', 'host')
    remote_path = config.get('transfer', 'path')
    service_name = config.get('transfer', 'service')

    remote_target = \
        remote_protocol + "://" + remote_host + "/" + remote_path + "/" + \
        prev_month.strftime('%Y') + "/"

    if run_mode == 'weekly':
        remote_target += run_mode + "/" + prev_month.strftime('%V') + "/"
    elif run_mode == 'monthly':
        remote_target += run_mode + "/" + prev_month.strftime('%m') + "/"
    else:
        raise RuntimeError('Undefined run_mode detected: %s' % run_mode)

    remote_target += service_name + "/"

    for report_path in reports_path_list:

        if not os.path.isfile(report_path):
            raise RuntimeError('Report file was not found: %s' % report_path)

        logging.debug('rsync %s %s' % (report_path, remote_target))

        try:

            output = subprocess.check_output(
                ["rsync", report_path, remote_target], stderr=subprocess.STDOUT)

            logging.debug(output)

        except subprocess.CalledProcessError as e:
            raise RuntimeError(e.output)


def main():

    parser = argparse.ArgumentParser(description='Storage Report Generator.')
    parser.add_argument('-f', '--config-file', dest='config_file', type=str, required=True, help='Path of the config file.')
    parser.add_argument('-D', '--enable-debug', dest='enable_debug', required=False, action='store_true', help='Enables logging of debug messages.')
    parser.add_argument('-L', '--enable-local', dest='enable_local', required=False, action='store_true', help='Enables local program execution.')

    args = parser.parse_args()

    if not os.path.isfile(args.config_file):
        raise IOError("The config file does not exist or is not a file: " + args.config_file)

    logging_level = logging.INFO

    if args.enable_debug:
        logging_level = logging.DEBUG

    logging.basicConfig(level=logging_level, format='%(asctime)s - %(levelname)s: %(message)s')

    logging.info('START')

    try:
        check_matplotlib_version()

        # Commandline parameter.
        local = args.enable_local

        # Config file parameter.
        config = ConfigParser.ConfigParser()
        config.read(args.config_file)

        run_mode = config.get('execution', 'mode')
        time_format = config.get('execution', 'time_format')

        chart_dir = config.get('base_chart', 'report_dir')
        long_name = config.get('storage', 'long_name')

        prev_month = calc_prev_month_datetime()

        reports_path_list = None
        time_point = None

        if run_mode == 'weekly':

            time_point = prev_month.strftime(time_format)

            reports_path_list = \
                create_weekly_reports(
                    local, chart_dir, long_name, time_point, config)

        elif run_mode == 'monthly':
            reports_path_list = create_monthly_reports()

        else:
            raise RuntimeError('Undefined run_mode detected: %s' % run_mode)

        transfer_reports(run_mode, prev_month, config, reports_path_list)

        logging.info('END')

        return 0
   
    except Exception as e:

        exc_type, exc_obj, exc_tb = sys.exc_info()
        filename = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]

        logging.error("Caught exception (%s): %s - %s (line: %s)"
                      % (exc_type, str(e), filename, exc_tb.tb_lineno))


if __name__ == '__main__':
   main()
