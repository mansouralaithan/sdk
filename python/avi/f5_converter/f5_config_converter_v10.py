import copy
import numbers
import logging
import os
import csv
import converter_constants as final

LOG = logging.getLogger("converter-log")
csv_writer = None


def get_port_by_protocol(protocol):
    """
    Instead of default ports for protocols F5 config has protocol in
    destination value for Avi object need to conver it to port number
    :param protocol: protocol name
    :return: integer value for protocol
    """
    port = final.DEFAULT_PORT
    if protocol == "https":
        port = final.HTTPS_PORT
    elif protocol == "ftp":
        port = final.FTP_PORT
    elif protocol == "smtp":
        port = final.SMTP_PORT
    elif protocol == "snmp":
        port = final.SNMP_PORT
    elif protocol == "telnet":
        port = final.TELNET_PORT
    elif protocol == "snmp-trap":
        port = final.SNMP_TRAP_PORT
    elif protocol == "ssh":
        port = final.SSH_PORT
    return port


def upload_file(file_path):
    """
    Reads the given file and returns the UTF-8 string
    :param file_path: Path of file to read
    :return: UTF-8 string read from file
    """
    file_str = None
    try:
        with open(file_path, "r") as file_obj:
            file_str = file_obj.read()
            file_str = file_str.decode("utf-8")
    except UnicodeDecodeError as ude:
        try:
            file_str = file_str.decode('latin-1')
        except:
            LOG.error("Error to read file %s" % file_path, exc_info=True)
    except:
        LOG.error("Error to read file %s" % file_path, exc_info=True)
    return file_str


def update_skipped_attributes(skipped, indirect_list, ignore_dict, object):
    indirect_mappings = [attr for attr in indirect_list if attr in skipped]
    skipped = [attr for attr in skipped if attr not in indirect_list]
    for key in ignore_dict.keys():
        if key in object and key in skipped and object[key] == ignore_dict[key]:
            skipped.remove(key)
    return skipped, indirect_mappings


def remove_dup_key(obj_list):
    for obj in obj_list:
        obj.pop('dup_of', None)


def update_for_duplicates(obj_list):
    for src_obj in obj_list:
        for tmp_obj in obj_list:
            if not src_obj["name"] == tmp_obj["name"]:
                src_cp = copy.deepcopy(src_obj)
                tmp_cp = copy.deepcopy(tmp_obj)
                del src_cp["name"]
                if "description" in src_cp:
                    del src_cp["description"]
                del tmp_cp["name"]
                if "description" in tmp_cp:
                  del tmp_cp["description"]
                dup_lst = src_cp.pop("dup_of", [])
                if cmp(src_cp, tmp_cp) == 0:
                    dup_lst.append(tmp_obj["name"])
                    src_obj["dup_of"] = dup_lst
                    obj_list.remove(tmp_obj)


def convert_servers_config(servers_config):
    """
    Converts the config of servers in the pool
    :param servers_config: F5 servers config for particular pool
    :return: List of Avi server configs
    """
    server_list = []
    skipped_list = []
    supported_attributes = ['session']
    for server_name in servers_config.keys():
        skipped = None
        server = servers_config[server_name]
        parts = server_name.split(':')
        ip_addr = parts[0]
        port = parts[1] if len(parts) == 2 else final.DEFAULT_PORT
        if not port.isdigit():
            port = get_port_by_protocol(port)
        enabled = True
        state = 'enabled'
        if server:
            state = server.get("session", 'enabled')
            skipped = [key for key in server.keys()
                       if key not in supported_attributes]
        if state == "user disabled":
            enabled = False
        server_list.append({
            'ip': {
                'addr': ip_addr,
                'type': 'V4'
            },
            'port': port,
            'enabled': enabled
        })

        if skipped:
            skipped_list.append({server_name: skipped})
    return server_list, skipped_list


def get_avi_pool_down_action(action):
    """
    Maps Pool down action from F5 config to Avi Config
    :param action: F5 action string
    :return: Avi action String
    """
    action_close_con = {
        "type": "FAIL_ACTION_CLOSE_CONN"
    }
    if action == "reset":
        return action_close_con
    if action == "reselect":
        return action_close_con
    else:
        return action_close_con


def get_avi_lb_algorithm(f5_algorithm):
    """
    Converts f5 LB algorithm to equivalent avi LB algorithm
    :param f5_algorithm: f5 algorithm name
    :return: Avi LB algorithm enum value
    """
    avi_algorithm = None
    if not f5_algorithm or f5_algorithm in ["ratio", "member ratio"]:
        avi_algorithm = "LB_ALGORITHM_ROUND_ROBIN"
    elif f5_algorithm in ["member least conn", "least conn",
                          "weighted least conn member", "l3 addr"
                          "weighted least conn node addr", "least sessions"]:
        avi_algorithm = "LB_ALGORITHM_LEAST_CONNECTIONS"
    elif f5_algorithm in ["fastest", "fastest app resp"]:
        avi_algorithm = "LB_ALGORITHM_FASTEST_RESPONSE"
    elif f5_algorithm in ["dynamic ratio", "member observed", "predictive",
                          "member predictive", "observed",
                          "member dynamic ratio"]:
        avi_algorithm = "LB_ALGORITHM_LEAST_LOAD"
    return avi_algorithm


def convert_pool_config(pool_config, monitor_config_list):
    """
    Convert list of pools from F5 config to Avi config
    :param pool_config: F5 pool config
    :param monitor_config_list: Avi monitor config list
    :return: List of pools converted to Avi configuration
    """
    pool_list = []
    supported_attr = ['members', 'monitor', 'action on svcdown', 'lb method',
                      'description']
    for pool_name in pool_config.keys():
        LOG.debug("Converting Pool: %s" % pool_name)
        try:
            skipped = []
            f5_pool = pool_config[pool_name]
            if not f5_pool:
                LOG.debug("Empty pool skipped for conversion :" + pool_name)
                add_status_row('pool', None, pool_name, 'skipped', None, None)
                continue
            servers, member_skipped_config = convert_servers_config(
                f5_pool.get("members", {}))
            sd_action = f5_pool.get("action on svcdown", "")
            pd_action = get_avi_pool_down_action(sd_action)
            lb_method = f5_pool.get("lb method", None)
            lb_algorithm = get_avi_lb_algorithm(lb_method)
            description = f5_pool.get('description', None)
            pool_obj = {
                    "name": pool_name,
                    "description": description,
                    "servers": servers,
                    "fail_action": pd_action,
                    "lb_algorithm": lb_algorithm
                }
            monitor_names = f5_pool.get("monitor", None)
            skipped_monitors = []
            if monitor_names:
                monitors = monitor_names.split(" ")
                monitor_refs = []
                for monitor in monitors:
                    if monitor in ["and", "all", "min", "of", "none"] \
                            or monitor.isdigit():
                        continue
                    monitor_obj = [obj for obj in monitor_config_list
                                   if obj["name"] == monitor]
                    if monitor_obj:
                        monitor_refs.append(monitor_obj[0]["name"])
                    else:
                        LOG.warning("Monitor %s not found for pool %s"
                                    % (monitor, pool_name))
                        skipped_monitors.append(monitor)
                pool_obj["health_monitor_refs"] = monitor_refs
            pool_list.append(pool_obj)
            skipped_attr = [key for key in f5_pool.keys() if
                            key not in supported_attr]
            if skipped_attr:
                skipped.append(skipped_attr)
            if member_skipped_config:
                skipped.append(member_skipped_config)
            if skipped_monitors:
                skipped.append({"monitors": skipped_monitors})
            if skipped:
                add_status_row('pool', None, pool_name, 'partial',
                               skipped, pool_obj)
            else:
                add_status_row('pool', None, pool_name, 'successful',
                               skipped, pool_obj)
        except:
            LOG.error("Failed to convert pool: %s" % pool_name, exc_info=True)
            add_status_row('pool', None, pool_name, 'Error')
        LOG.debug("Conversion successful for Pool: %s" % pool_name)
    return pool_list


def get_monitor_defaults(f5_monitor, monitor_config, monitor_name):
    """
    Monitor can have inheritance used by attribute defaults-from in F5
    configuration this method recursively gets all the attributes from the
    default objects and forms complete object
    :param f5_monitor: F5 monitor object
    :param monitor_config: List of F5 monitor configs
    :param monitor_name: There is no attribute in config to determine type of
    monitor it can be mapped from root monitors name
    :return:
    """
    parent_name = f5_monitor.get("defaults from", None)
    if parent_name:
        parent_monitor = monitor_config.get(parent_name, None)
        if parent_monitor:
            parent_monitor = get_monitor_defaults(
                parent_monitor, monitor_config, parent_name)
            parent_monitor = copy.deepcopy(parent_monitor)
            parent_monitor.update(f5_monitor)
            f5_monitor = parent_monitor
    else:
        f5_monitor["type"] = monitor_name
    return f5_monitor


def convert_monitor_entity(name, f5_monitor, file_location):
    """
    Conversion of single F5 monitor object to Avi health monitor object
    :param name: name of health monitor
    :param f5_monitor: F5 monitor config object
    :param file_location: External monitor script file location
    :return: Avi monitor config object
    """
    reverse = f5_monitor.get("reverse", None)
    if reverse:
        parts = reverse.rsplit(" ")
        f5_monitor[parts[0]] = parts[1]
        f5_monitor["reverse"] = None
    supported_attributes = ["timeout", "interval", "time until up",
                            "description", "type", "defaults from"]
    skipped = [key for key in f5_monitor.keys()
               if key not in supported_attributes]
    timeout = int(f5_monitor.get("timeout", final.DEFAULT_TIMEOUT))
    interval = int(f5_monitor.get("interval", final.DEFAULT_INTERVAL))
    time_until_up = int(f5_monitor.get("time until up",
                                       final.DEFAULT_TIME_UNTIL_UP))
    successful_checks = int(timeout/interval)
    failed_checks = final.DEFAULT_FAILED_CHECKS
    if time_until_up > 0:
        failed_checks = int(time_until_up/interval)
        failed_checks = 1 if failed_checks == 0 else failed_checks
    description = f5_monitor.get("description", None)
    monitor_dict = dict()
    monitor_dict["name"] = name
    monitor_dict["receive_timeout"] = interval-1
    monitor_dict["failed_checks"] = failed_checks
    monitor_dict["send_interval"] = interval
    monitor_dict["successful_checks"] = successful_checks
    if description:
        monitor_dict["description"] = description

    if f5_monitor["type"] == "http":
        http_attr = ["recv", "recv disable", "reverse", "send"]
        skipped = [key for key in skipped if key not in http_attr]
        send = f5_monitor.get('send', 'HEAD / HTTP/1.0')
        monitor_dict["type"] = "HEALTH_MONITOR_HTTP"
        monitor_dict["http_monitor"] = {
            "http_request": send,
            "http_response_code": ["HTTP_2XX", "HTTP_3XX"]
        }
        maintenance_response = None
        if "reverse" in f5_monitor.keys():
            maintenance_response = f5_monitor.get("recv", None)
        elif "recv disable" in f5_monitor.keys():
            maintenance_response = f5_monitor.get("recv disable", None)
        if maintenance_response.replace('\"', '').strip():
            maintenance_response = \
                maintenance_response.replace('\"', '').strip()
            monitor_dict["http_monitor"]["maintenance_response"] = \
                maintenance_response

    elif f5_monitor["type"] == "https":
        https_attr = ["recv", "recv disable", "reverse", "send"]
        skipped = [key for key in skipped if key not in https_attr]
        send = f5_monitor.get('send', None)
        monitor_dict["type"] = "HEALTH_MONITOR_HTTPS"
        monitor_dict["https_monitor"] = {
            "http_request": send,
            "http_response_code": ["HTTP_2XX", "HTTP_3XX"]
        }
        maintenance_response = None
        if "reverse" in f5_monitor.keys():
            maintenance_response = f5_monitor.get("recv", None)
        elif "recv disable" in f5_monitor.keys():
            maintenance_response = f5_monitor.get("recv disable", None)
        if maintenance_response.replace('\"', '').strip():
            maintenance_response = \
                maintenance_response.replace('\"', '').strip()
            monitor_dict["https_monitor"]["maintenance_response"] = \
                maintenance_response
    elif f5_monitor["type"] == "tcp":
        tcp_attr = ["dest", "send", "recv", "recv disable", "reverse"]
        skipped = [key for key in skipped if key not in tcp_attr]
        destination = f5_monitor.get("dest", "*:*")
        dest_str = destination.split(":")
        if len(dest_str) > 1 and isinstance(dest_str[1], numbers.Integral):
            monitor_dict["monitor_port"] = dest_str[1]
        monitor_dict["type"] = "HEALTH_MONITOR_TCP"
        request = f5_monitor.get("send", None)
        response = f5_monitor.get("recv", None)
        tcp_monitor = None
        if request or response:
            request = request.replace('\"', '') if request else None
            response = response.replace('\"', '') if response else None
            tcp_monitor = {"tcp_request": request, "tcp_response": response}
            monitor_dict["tcp_monitor"] = tcp_monitor
        maintenance_response = None
        if "reverse" in f5_monitor.keys():
            maintenance_response = f5_monitor.get("recv", None)
        elif "recv disable" in f5_monitor.keys():
            maintenance_response = f5_monitor.get("recv disable", None)
        if maintenance_response.replace('\"', '').strip():
            maintenance_response = \
                maintenance_response.replace('\"', '').strip()
            if tcp_monitor:
                tcp_monitor["maintenance_response"] = maintenance_response
            else:
                tcp_monitor = {"maintenance_response": maintenance_response}
                monitor_dict["tcp_monitor"] = tcp_monitor
    elif f5_monitor["type"] == "udp":
        udp_attr = ["dest", "send", "recv", "recv disable", "reverse"]
        skipped = [key for key in skipped if key not in udp_attr]
        destination = f5_monitor.get("dest", "*:*")
        dest_str = destination.split(":")
        if len(dest_str) > 1 and isinstance(dest_str[1], numbers.Integral):
            monitor_dict["monitor_port"] = dest_str[1]
        monitor_dict["type"] = "HEALTH_MONITOR_UDP"
        request = f5_monitor.get("send", None)
        response = f5_monitor.get("recv", None)
        udp_monitor = None
        if request or response:
            request = request.replace('\"', '') if request else None
            response = response.replace('\"', '') if response else None
            udp_monitor = {"udp_request": request, "udp_response": response}
            monitor_dict["udp_monitor"] = udp_monitor
        maintenance_response = None
        if "reverse" in f5_monitor.keys():
            maintenance_response = f5_monitor.get("recv", None)
        elif "recv disable" in f5_monitor.keys():
            maintenance_response = f5_monitor.get("recv disable", None)
        if maintenance_response.replace('\"', '').strip():
            maintenance_response = \
                maintenance_response.replace('\"', '').strip()
            if udp_monitor:
                udp_monitor["maintenance_response"] = maintenance_response
            else:
                udp_monitor = {"maintenance_response": maintenance_response}
                monitor_dict["udp_monitor"] = udp_monitor
    elif f5_monitor["type"] in ["gateway_icmp", "icmp"]:
        monitor_dict["type"] = "HEALTH_MONITOR_PING"
    elif f5_monitor["type"] == "external":
        script_vars = ""
        ext_attr = ["run", "args", "user-defined"]
        for key in f5_monitor.keys():
            if key not in ('args', 'run') and '\"' in f5_monitor[key]:
                ext_attr.append(key)
                param_value = f5_monitor[key].replace('\"', '')
                script_vars += "%s=%s," % (key, param_value)
        if script_vars:
            script_vars = script_vars[:-1]
        skipped = [key for key in skipped if key not in ext_attr]
        cmd_code = f5_monitor.get("run", None)
        cmd_params = f5_monitor.get("args", None)
        cmd_code = cmd_code.replace('\"', '') if cmd_code else None
        cmd_params = cmd_params.replace('\"', '') if cmd_params else None
        if cmd_code:
            cmd_code = upload_file(file_location+os.path.sep+cmd_code)
        else:
            LOG.warn("Skipped monitor: %s for no value in run attribute" % name)
            add_status_row("monitor", "external", name, "error")
            return None, None
        monitor_dict["type"] = "HEALTH_MONITOR_EXTERNAL"
        ext_monitor = {
            "command_code": cmd_code,
            "command_parameters": cmd_params,
            "command_variables": script_vars
        }
        monitor_dict["external_monitor"] = ext_monitor
    return monitor_dict, skipped


def convert_monitor_config(monitor_config, file_location):
    """
    Convert F5 monitor config dict to Avi health monitor config list
    :param monitor_config: F5 monitor config dict
    :param file_location: External monitor script file location
    :return: List of Avi health monitor objects
    """
    monitor_list = []
    supported_types = ["http", "https", "dns", "external", "tcp", "udp",
                       "gateway_icmp", "icmp"]
    for key in monitor_config.keys():
        try:
            LOG.debug("Converting monitor: %s" % key)
            f5_monitor = monitor_config[key]
            if not f5_monitor:
                add_status_row('monitor', '', key, 'skipped', None, None)
                continue
            f5_monitor = get_monitor_defaults(f5_monitor, monitor_config,
                                              f5_monitor.get("defaults from",
                                                             key))
            if f5_monitor["type"] not in supported_types:
                LOG.warn("Monitor type not supported by Avi : "+key)
                add_status_row('monitor', f5_monitor["type"], key, 'skipped',
                               None, None)
                continue
            avi_monitor, skipped = convert_monitor_entity(key, f5_monitor,
                                                          file_location)
            if not avi_monitor:
                continue
            indirect_mappings = ["up interval", "debug", "ip dscp"]
            skipped, indirect_list = update_skipped_attributes(
                skipped, indirect_mappings, {}, f5_monitor)
            if skipped:
                add_status_row('monitor', f5_monitor["type"], key, 'partial',
                               skipped, avi_monitor, indirect_list)
            else:
                add_status_row('monitor', f5_monitor["type"], key, 'successful',
                               None, avi_monitor, indirect_list)
            monitor_list.append(avi_monitor)
        except:
            LOG.error("Failed to convert monitor: %s" % key, exc_info=True)
            add_status_row('monitor', key, key, 'Error')
        LOG.debug("Conversion successful for monitor: %s" % key)
    return monitor_list


def get_key_cert_obj(name, key_file_name, cert_file_name, folder_path, option):
    """
    Read key and cert files from given location and construct avi
    SSLKeyAndCertificate objects
    :param name: SSLKeyAndCertificate object name
    :param key_file_name: key file name
    :param cert_file_name: cert file name
    :param folder_path: location of key and cert files
    :param option: api-upload or cli-file both requires different
    object structure
    :return:SSLKeyAndCertificate object
    """
    key = None
    cert = None
    key_file_name = key_file_name.replace('\"', '')
    cert_file_name = cert_file_name.replace('\"', '')
    if cert_file_name or key_file_name:
        folder_path = folder_path+os.path.sep
        key = upload_file(folder_path+key_file_name)
        cert = upload_file(folder_path+cert_file_name)
    ssl_kc_obj = None
    if key and cert:
        if option == "cli-upload":
            cert = {"certificate": cert}
        ssl_kc_obj = {
                'name': name,
                'key': key,
                'certificate': cert,
                'key_passphrase': ''
            }
    return ssl_kc_obj


def update_with_default_profile(profile_type, profile, profile_config):
    """
    Profiles can have inheritance used by attribute defaults-from in F5
    configuration this method recursively gets all the attributes from the
    default objects and forms complete object
    :param profile_type: type of profile
    :param profile: currant profile object
    :param profile_config: F5 profile config dict
    :return: Complete profile with updated attributes from defaults
    """
    parent_name = profile.get("defaults from", None)
    if parent_name:
        parent_profile = profile_config.get(profile_type + " " +
                                            parent_name, None)
        if parent_profile:
            parent_profile = update_with_default_profile(
                profile_type, parent_profile, profile_config)
            parent_profile = copy.deepcopy(parent_profile)
            parent_profile.update(profile)
            profile = parent_profile
    return profile


def convert_http_profile(profile, name):
    """
    Converts HTTP f5 profile config to Avi HTTP profile config with
    caching and compression config
    :param profile: F5 http profile config
    :param name: http profile name
    :return: Avi http profile config
    """
    supported_attr = ["insert xforwarded for", "xff alternative names",
                      "max header size", "ramcache min object size",
                      "ramcache max age", "ramcache max object size",
                      "ramcache insert age header", "oneconnect transformations"
                      "compress keep accept encoding", "ramcache uri exclude",
                      "compress content type include", "ramcache uri include",
                      "compress browser workarounds", "ramcache size",
                      "encrypt cookies", "fallback"]
    skipped = [key for key in profile.keys()
               if key not in supported_attr]
    app_profile = dict()
    sg_obj = None
    app_profile['name'] = name
    app_profile['type'] = 'APPLICATION_PROFILE_TYPE_HTTP'
    http_profile = dict()
    encpt_cookie = profile.get('encrypt cookies', 'none')
    encpt_cookie = False if encpt_cookie == 'none' else True
    con_mltplxng = profile.get('oneconnect transformations', 'disabled')
    con_mltplxng = False if con_mltplxng == 'disabled' else True
    http_profile['x_forwarded_proto_enabled'] = profile.get(
        'insert xforwarded for', False)
    http_profile['xff_alternate_name'] = profile.get('xff alternative names',
                                                     None)
    header_size = profile.get('max header size', final.DEFAULT_MAX_HEADER)
    http_profile['client_max_header_size'] = int(header_size)/final.BYTES_IN_KB
    http_profile['connection_multiplexing_enabled'] = con_mltplxng
    http_profile['secure_cookie_enabled'] = encpt_cookie
    app_profile["http_profile"] = http_profile
    fallback_host = profile.get("fallback", 'none')
    fallback_host = None if fallback_host == 'none' else fallback_host

    cache = profile.get('ramcache', 'disable')
    if not cache == 'disable':
        cache_config = dict()
        cache_config['min_object_size'] = profile.get(
            'ramcache min object size', final.MIN_CACHE_OBJ_SIZE)
        cache_config['query_cacheable'] = True
        cache_config['max_object_size'] = profile.get(
            'ramcache max object size', final.MAX_CACHE_OBJ_SIZE)
        age_header = profile.get('ramcache insert age header', 'disable')
        if age_header == 'enable':
            cache_config['age_header'] = True
        else:
            cache_config['age_header'] = False
        cache_config['enabled'] = True
        cache_config['default_expire'] = profile.get(
            'ramcache max age', final.DEFAULT_CACHE_MAX_AGE)
        exclude_uri = profile.get("ramcache uri exclude", None)
        include_uri = profile.get("ramcache uri include", None)
        if exclude_uri and isinstance(exclude_uri, dict):
            exclude_uri = exclude_uri.keys() + exclude_uri.values()
            if None in exclude_uri:
                exclude_uri.remove(None)
            cache_config['mime_types_black_list'] = exclude_uri
        if include_uri and isinstance(include_uri, dict):
            include_uri = include_uri.keys() + include_uri.values()
            if None in include_uri:
                include_uri.remove(None)
            cache_config['mime_types_list'] = include_uri
        http_profile["cache_config"] = cache_config
    compression = profile.get('compress', 'disable')
    if not compression == 'disable':
        compression_profile = dict()
        compression_profile["type"] = "AUTO_COMPRESSION"
        compression_profile["compression"] = True
        encoding = profile.get("compress keep accept encoding", "disable")
        if encoding == "disable":
            encoding = True
        else:
            encoding = False
        compression_profile["remove_accept_encoding_header"] = encoding
        content_type = profile.get("compress content type include", "")
        if content_type:
            content_types = content_type.keys()+content_type.values()
            sg_obj = {
                "kv": [],
                "type": "SG_TYPE_STRING",
                "name": name+"-content_type"
            }
            uris = []
            for content_type in content_types:
                uri = {"key": content_type}
                uris.append(uri)
            sg_obj["kv"] = uris

            compression_profile["compressible_content_ref"]\
                = name + "-content_type"
        http_profile["compression_profile"] = compression_profile
    app_profile["http_profile"] = http_profile
    return app_profile, sg_obj, skipped, fallback_host


def get_cc_algo_val(cc_algo):
    avi_algo_val = "CC_ALGO_NEW_RENO"
    if cc_algo == "high-speed":
        avi_algo_val = "CC_ALGO_HTCP"
    elif cc_algo == "cubic":
        avi_algo_val = "CC_ALGO_CUBIC"
    return avi_algo_val


def convert_profile_config(profile_config, certs_location, option):
    """
    Converts F5 profiles to equivalent Avi profiles
    :param profile_config: F5 Profile config dict
    :param certs_location: location of cert and key file location
    :param option: api-upload or cli-file both requires different
    object structure
    :return:
    """
    ssl_key_cert_list = []
    app_profile_list = []
    ssl_profile_list = []
    pki_profile_list = []
    persist_profile_list = []
    string_group = []
    hash_algorithm = []
    network_profile_list = []
    fallback_host_dict = {}
    supported_types = ["clientssl", "serverssl", "http", "dns",
                       "persist", "fastL4", "fasthttp", "tcp", "udp"]
    for key in profile_config.keys():
        profile_type = None
        name = None
        try:
            converted_objs = []
            indirect = []
            ignore_for_defaults = {}
            profile_type, name = key.split(" ")
            if profile_type not in supported_types:
                LOG.warning("Skipped not supported profile: %s of type: %s" %
                            (name, profile_type))
                add_status_row('profile', profile_type, name, 'skipped')
                continue
            LOG.debug("Converting profile: %s" % name)
            profile = profile_config[key]
            profile = update_with_default_profile(profile_type,
                                                  profile, profile_config)
            skipped = profile.keys()
            if profile_type in ("clientssl", "serverssl"):
                supported_attr = ["cert", "key", "ciphers", "unclean shutdown",
                                  "crl file", "ca file", "defaults from",
                                  "options"]
                skipped = [attr for attr in profile.keys()
                           if attr not in supported_attr]
                key_cert_obj = None
                cert_file = profile.get("cert", None)
                key_file = profile.get("key", None)
                key_file = None if key_file == 'none' else key_file
                cert_file = None if cert_file == 'none' else cert_file
                if key_file and cert_file:
                    key_cert_obj = get_key_cert_obj(
                        name, key_file, cert_file, certs_location, option)
                if key_cert_obj:
                    ssl_key_cert_list.append(key_cert_obj)
                    converted_objs.append({'key_cert': key_cert_obj})
                ciphers = profile.get('ciphers', 'DEFAULT')
                ciphers = ciphers.replace('\"', '')
                ciphers = 'AES:3DES:RC4' if ciphers in ['DEFAULT',
                                                        'NATIVE'] else ciphers
                ciphers = ciphers.replace(":@SPEED", "")
                ssl_profile = dict()
                ssl_profile['name'] = name
                ssl_profile['accepted_ciphers'] = ciphers
                close_notify = profile.get('unclean shutdown', None)
                if close_notify and close_notify == 'enabled':
                    ssl_profile['send_close_notify'] = True
                else:
                    ssl_profile['send_close_notify'] = False
                ssl_profile_list.append(ssl_profile)
                converted_objs.append({'ssl_profile': ssl_profile})
                options = profile.get("options", "")
                if isinstance(options, dict):
                    opt = []
                    for opt_key in options.keys():
                        opt.append(opt_key+' '+options[opt_key])
                    options = opt
                accepted_versions = []
                if "no tlsv1" not in options:
                    accepted_versions.append({"type": "SSL_VERSION_TLS1"})
                if "no tlsv1.1" not in options:
                    accepted_versions.append({"type": "SSL_VERSION_TLS1_1"})
                if "no tlsv1.2" not in options:
                    accepted_versions.append({"type": "SSL_VERSION_TLS1_2"})
                if accepted_versions:
                    ssl_profile["accepted_versions"] = accepted_versions

                crl_file_name = profile.get('crl file', None)
                ca_file_name = profile.get('ca file', None)
                if crl_file_name and crl_file_name != 'none':
                    crl_file_name = crl_file_name.replace('\"', '').strip()
                else:
                    crl_file_name = None
                if ca_file_name and ca_file_name != 'none':
                    ca_file_name = ca_file_name.replace('\"', '').strip()
                else:
                    ca_file_name = None
                if ca_file_name and crl_file_name:
                    pki_profile = dict()
                    file_path = certs_location+os.path.sep+ca_file_name
                    pki_profile["name"] = name
                    error = False
                    ca = upload_file(file_path)
                    if ca:
                        pki_profile["ca_certs"] = [{'certificate': ca}]
                    else:
                        error = True
                    file_path = certs_location+os.path.sep+crl_file_name
                    crl = upload_file(file_path)
                    if crl:
                        pki_profile["crls"] = [{'body': crl}]
                    else:
                        error = True
                    if not error:
                        pki_profile_list.append(pki_profile)
                        converted_objs.append({'pki_profile': pki_profile})
                elif ca_file_name:
                    LOG.warn("crl-file missing hence skipped ca-file")
                    skipped.append("ca-file")
            elif profile_type == 'http':
                app_profile, sg_obj, skipped, fallback_host = \
                    convert_http_profile(profile, name)
                if fallback_host:
                    fallback_host_dict[name] = fallback_host
                indirect = ["lws width", "lws separator", "max requests",
                            "compress browser workarounds", "cache size",
                            "compress uri include", "ramcache aging rate",
                            "compress gzip window size", "compress gzip level"]
                ignore_for_defaults = {'compress uri exclude': 'none'}
                if sg_obj:
                    string_group.append(sg_obj)
                    converted_objs.append({'string_group': sg_obj})
                app_profile_list.append(app_profile)
                converted_objs.append({'app_profile': app_profile})
            elif profile_type == 'dns':
                supported_attr = ["description", "defaults from"]
                skipped = [attr for attr in profile.keys()
                           if attr not in supported_attr]
                app_profile = dict()
                app_profile['name'] = name
                app_profile['type'] = 'APPLICATION_PROFILE_TYPE_DNS'
                app_profile_list.append(app_profile)
                converted_objs.append({'app_profile': app_profile})
            elif profile_type == 'fastL4':
                supported_attr = ["idle timeout", "software syncookie",
                                  "defaults from"]
                indirect = ["reset on timeout", "pva acceleration"]
                skipped = [attr for attr in profile.keys()
                           if attr not in supported_attr]
                syn_protection = (profile.get("software syncookie", None) ==
                                  'enabled')
                description = profile.get('description', None)
                timeout = profile.get("idle timeout", final.MIN_SESSION_TIMEOUT)
                if timeout < 60:
                    timeout = final.MIN_SESSION_TIMEOUT
                    LOG.warn("idle-timeout for profile: %s is less" % name +
                    " than minimum, changed to Avis minimum value")
                elif timeout > final.MAX_SESSION_TIMEOUT:
                    timeout = final.MAX_SESSION_TIMEOUT
                    LOG.warn("idle-timeout for profile: %s  is grater" % name +
                    " than maximum, changed to Avis maximum value")
                ntwk_profile = {
                    "profile": {
                        "tcp_fast_path_profile": {
                          "session_idle_timeout": timeout,
                          "enable_syn_protection": syn_protection
                        },
                        "type": "PROTOCOL_TYPE_TCP_FAST_PATH"
                    },
                    "name": name,
                    "description": description
                }
                app_profile = {
                    "type": "APPLICATION_PROFILE_TYPE_L4",
                    "name": name,
                    "description": description
                }
                network_profile_list.append(ntwk_profile)
                app_profile_list.append(app_profile)
                converted_objs.append({'network_profile': ntwk_profile})
            elif profile_type == 'fasthttp':
                supported_attr = ["description", "idle timeout",
                                  "defaults from"]
                indirect = ["reset on timeout"]
                skipped = [attr for attr in profile.keys()
                           if attr not in supported_attr]
                timeout = profile.get("idle-timeout", 0)
                ntwk_profile = {
                    "profile": {
                        "tcp_proxy_profile": {
                            "idle_connection_timeout": timeout
                        },
                        "type": "PROTOCOL_TYPE_TCP_PROXY"
                    },
                    "name": name
                }
                network_profile_list.append(ntwk_profile)
                converted_objs.append({'network_profile': ntwk_profile})
            elif profile_type == 'tcp':
                supported_attr = ["description", "idle timeout", "nagle",
                                  "max retrans syn", "time wait recycle",
                                  "time wait", "congestion control",
                                  "recv window", "max retrans"]
                indirect = ["reset on timeout", "slow start"]
                skipped = [attr for attr in profile.keys()
                           if attr not in supported_attr]
                timeout = profile.get("idle timeout", 0)
                nagle = profile.get("nagle", 'disabled')
                nagle = False if nagle == 'disabled' else True
                retrans = profile.get("max retrans", final.MIN_SYN_RETRANS)
                retrans = final.MIN_SYN_RETRANS if \
                    int(retrans) < final.MIN_SYN_RETRANS else retrans
                retrans = final.MAX_SYN_RETRANS if \
                    int(retrans) > final.MAX_SYN_RETRANS else retrans
                syn_retrans = profile.get("max retrans syn",
                                          final.MIN_SYN_RETRANS)
                syn_retrans = final.MIN_SYN_RETRANS \
                    if int(syn_retrans) < final.MIN_SYN_RETRANS else syn_retrans
                syn_retrans = final.MAX_SYN_RETRANS \
                    if int(syn_retrans) > final.MAX_SYN_RETRANS else syn_retrans
                conn_type = profile.get("time wait recycle", "disabled")
                conn_type = "CLOSE_IDLE" if \
                    conn_type == "disabled" else "KEEP_ALIVE"
                delay = profile.get("time wait", 0)
                window = profile.get("recv window",
                                     (final.MIN_RECV_WIN * final.BYTES_IN_KB))
                window = int(int(window)/final.BYTES_IN_KB)
                cc_algo = profile.get("congestion-control", "")
                cc_algo = get_cc_algo_val(cc_algo)
                ntwk_profile = {
                    "profile": {
                        "tcp_proxy_profile": {
                            "idle_connection_timeout": timeout,
                            "nagles_algorithm": nagle,
                            "max_syn_retransmissions": syn_retrans,
                            "max_retransmissions": retrans,
                            "idle_connection_type": conn_type,
                            "time_wait_delay": delay,
                            "receive_window": window,
                            "cc_algo": cc_algo
                        },
                        "type": "PROTOCOL_TYPE_TCP_PROXY"
                    },
                    "name": name
                }
                network_profile_list.append(ntwk_profile)
                converted_objs.append({'network_profile': ntwk_profile})
            elif profile_type == 'udp':
                supported_attr = ["idle timeout", "datagram lb",
                                  "defaults from"]
                skipped = [attr for attr in profile.keys()
                           if attr not in supported_attr]
                per_pkt = profile.get("datagram lb", 'disable')
                timeout = profile.get("idle timeout", 0)
                ntwk_profile = {
                    "profile": {
                        "type": "PROTOCOL_TYPE_UDP_FAST_PATH",
                        "udp_fast_path_profile": {
                            "per_pkt_loadbalance": (per_pkt == 'enable'),
                            "session_idle_timeout": timeout
                        }
                    },
                    "name": name
                }
                network_profile_list.append(ntwk_profile)
                converted_objs.append({'network_profile': ntwk_profile})
            elif profile_type == 'persist':
                indirect = ["hash length", "hash offset"]
                ignore_for_defaults = {"mask": "none"}
                persist_mode = profile.get("mode")
                if persist_mode == "cookie":
                    supported_attr = ["cookie name", "mode", "defaults from",
                                      "cookie hash offset", "mirror",
                                      "cookie hash length"]
                    skipped = [attr for attr in profile.keys()
                               if attr not in supported_attr]
                    cookie_name = profile.get("cookie name", None)
                    timeout = profile.get("expiration", '1')
                    if ':' in str(timeout):
                        expiration = timeout.split(':')
                        expiration.reverse()
                        timeout = 0
                        i = 0
                        for val in expiration:
                            val = int(val)
                            if i == 0:
                                timeout = int(val/final.SEC_IN_MIN)
                            elif i == 1:
                                timeout += val
                            elif i == 2:
                                timeout += (val*final.MIN_IN_HR)
                            elif i == 3:
                                timeout += (val*final.MIN_IN_HR*final.HR_IN_DAY)
                                i += 1
                    else:
                        timeout = 1 if int(timeout) == 0 else timeout
                    if cookie_name == "none":
                        cookie_name = None
                    persist_profile = {
                        "name": name,
                        "app_cookie_persistence_profile": {
                            "prst_hdr_name": cookie_name,
                            "timeout": timeout
                        },
                        "server_hm_down_recovery": "HM_DOWN_PICK_NEW_SERVER",
                        "persistence_type": "PERSISTENCE_TYPE_APP_COOKIE",
                    }
                elif persist_mode == "ssl":
                    supported_attr = ["mode", "defaults from", "mirror"]
                    skipped = [attr for attr in profile.keys()
                               if attr not in supported_attr]
                    indirect.append("timeout")
                    persist_profile = {
                        "server_hm_down_recovery": "HM_DOWN_PICK_NEW_SERVER",
                        "persistence_type": "PERSISTENCE_TYPE_TLS",
                        "name": name
                    }
                elif persist_mode == "source addr":
                    supported_attr = ["timeout", "mode", "defaults from"]
                    skipped = [attr for attr in profile.keys()
                               if attr not in supported_attr]
                    timeout = profile.get("timeout", final.SOURCE_ADDR_TIMEOUT)
                    if timeout > 0:
                        timeout = int(timeout)/final.SEC_IN_MIN
                    persist_profile = {
                      "server_hm_down_recovery": "HM_DOWN_PICK_NEW_SERVER",
                      "persistence_type": "PERSISTENCE_TYPE_CLIENT_IP_ADDRESS",
                      "ip_persistence_profile": {
                        "ip_persistent_timeout": timeout
                      },
                      "name": name
                    }
                elif persist_mode == "hash":
                    hash_algorithm.append(name)
                    add_status_row('profile', "hash-persistence", name,
                                   'indirect-mapping', None,
                                   "Will be mapped to pools lb algorithm")
                    continue
                else:
                    LOG.error('persist mode not supported : %s' % name)
                    continue
                persist_profile_list.append(persist_profile)
                converted_objs.append({'persist_profile': persist_profile})
            skipped, indirect = update_skipped_attributes(
                    skipped, indirect, ignore_for_defaults, profile)
            if skipped:
                add_status_row('profile', profile_type, name, 'partial',
                               skipped, converted_objs, indirect)
            else:
                add_status_row('profile', profile_type, name, 'successful',
                               skipped, converted_objs, indirect)
        except:
            LOG.error("Failed to convert profile: %s" % key, exc_info=True)
            if name:
                add_status_row('profile', profile_type, name, 'Error')
            else:
                add_status_row('profile', key, key, 'Error')
        LOG.debug("Conversion successful for profile: %s" % name)
    avi_profiles = dict()
    avi_profiles["ssl_key_cert_list"] = ssl_key_cert_list
    avi_profiles["app_profile_list"] = app_profile_list
    avi_profiles["ssl_profile_list"] = ssl_profile_list
    avi_profiles["pki_profile_list"] = pki_profile_list
    avi_profiles["network_profile_list"] = network_profile_list
    avi_profiles["persist_profile_list"] = persist_profile_list
    return avi_profiles, string_group, hash_algorithm, fallback_host_dict


def get_profiles_for_vs(profiles, profile_config):
    """
    Searches for profile refs in converted profile config if not found creates
    default profiles
    :param profiles: profiles in f5 config assigned to VS
    :param profile_config: avi profile config
    :return: returns list of profile refs assigned to VS in avi config
    """
    vs_ssl_profile_names = []
    pool_ssl_profile_names = []
    app_profile_names = []
    network_profile_names = []
    if not profiles:
        profiles = dict()
    if isinstance(profiles, str):
        profiles = profiles.replace(" {}", "")
        profiles = {profiles: None}
    for name in profiles.keys():
        ssl_profile_list = profile_config.get("ssl_profile_list", [])
        ssl_profiles = [obj for obj in ssl_profile_list if
                        (obj['name'] == name or name in obj.get("dup_of", []))]
        if ssl_profiles:
            ssl_key_cert_list = profile_config.get("ssl_key_cert_list", [])
            key_cert = [obj for obj in ssl_key_cert_list if
                        (obj['name'] == name or name in obj.get("dup_of", []))]
            key_cert = key_cert[0]['name'] if key_cert else None
            profile = profiles.get(name, None)
            keys = profile.keys()
            pki_list = profile_config.get("pki_profile_list", [])
            pki_profiles = [obj for obj in pki_list if obj['name'] == name]
            if "clientside" in keys:
                vs_ssl_profile_names.append({"profile": ssl_profiles[0]["name"],
                                             "cert": key_cert,
                                             "pki": pki_profiles})
            elif "serverside" in keys:
                pool_ssl_profile_names.append(
                    {"profile": name, "cert": key_cert, "pki": pki_profiles})
        app_profiles = [obj for obj in profile_config["app_profile_list"]
                        if obj['name'] == name]
        if app_profiles:
            app_profile_names.append(name)
        ntwk_prof_lst = profile_config.get("network_profile_list", [])
        network_profiles = [obj for obj in ntwk_prof_lst if obj['name'] == name]
        if network_profiles:
            network_profile_names.append(name)
    if not app_profile_names:
        app_profile_names.append("http")
    return vs_ssl_profile_names, pool_ssl_profile_names, app_profile_names, \
           network_profile_names


def update_service(port, vs, enable_ssl):
    """
    iterates over services of existing vs in converted list to update
    services for port overlapping scenario
    :param port: port for currant VS
    :param vs: VS from converted config list
    :param enable_ssl: value to put in service object
    :return: boolean if service is updated or not
    """
    service_updated = False
    for service in vs['services']:
        port_end = service.get('port_range_end', None)
        if port_end and (service['port'] <= int(port) <= port_end):
            if port not in [1, 65535]:
                new_end = service['port_range_end']
                service['port_range_end'] = int(port)-1
                new_service = {'port': int(port)+1,
                               'port_range_end': new_end,
                               'enable_ssl': enable_ssl}
                vs['services'].append(new_service)
            elif port == 1:
                service['port'] = 2
            elif port == 65535:
                service['port_range_end'] = 65534
            service_updated = True
            break
    return service_updated


def get_service_obj(destination, vs_list, enable_ssl):
    """
    Checks port overlapping scenario for port value 0 in F5 config
    :param destination: IP and Port destination of VS
    :param vs_list: List of existing vs converted to avi config
    :param enable_ssl: value to put in service objects
    :return: List of services for VS
    """
    parts = destination.split(':')
    ip_addr = parts[0]
    port = parts[1] if len(parts) == 2 else 80
    if port == 'any':
        port = 0
    if isinstance(port, str) and (not port.isdigit()):
        port = get_port_by_protocol(port)

    vs_dup_ips = [vs for vs in vs_list if vs['ip_address']['addr'] == ip_addr]
    if int(port) > 0:
        for vs in vs_dup_ips:
            service_updated = update_service(port, vs, enable_ssl)
            if service_updated:
                break
        services_obj = [{'port': port, 'enable_ssl': enable_ssl}]
    else:
        used_ports = []
        for vs in vs_dup_ips:
            for service in vs['services']:
                used_ports.append(service['port'])
        if used_ports:
            services_obj = []
            if 65535 not in used_ports:
                used_ports.append(65536)
            used_ports = sorted(used_ports, key=int)
            start = 1
            for i in range(len(used_ports)):
                if start == used_ports[i]:
                    start += 1
                    continue
                end = int(used_ports[i])-1
                services_obj.append({'port': start,
                                     'port_range_end': end,
                                     'enable_ssl': enable_ssl})
                start = int(used_ports[i])+1
        else:
            services_obj = [{'port': 1, 'port_range_end': 65535,
                             'enable_ssl': enable_ssl}]
    return services_obj, ip_addr


def clone_pool(pool_name, vs_name, avi_pool_list):
    """
    If pool is shared with other VS pool is cloned for other VS as Avi dose not
    support shared pools with new pool name as <pool_name>-<vs_name>
    :param pool_name: Name of the pool to be cloned
    :param vs_name: Name of the VS for pool to be cloned
    :param avi_pool_list: new pool to be added to this list
    :return: new pool object
    """
    new_pool = None
    for pool in avi_pool_list:
        if pool["name"] == pool_name:
            new_pool = copy.deepcopy(pool)
            break
    if new_pool:
        new_pool["name"] = pool_name+"-"+vs_name
        avi_pool_list.append(new_pool)
        return new_pool["name"]


def update_pool_for_persist(avi_pool_list, pool_ref, persist_profile,
                            hash_profiles, persist_config):
    """
    Updates pool for persistence profile assigned in F5 VS config
    :param avi_pool_list: List of all converted pool objects to avi config
    :param pool_ref: pool name to be updated
    :param persist_profile: persistence profile to be added to pool
    :param hash_profiles: list of profile name for which pool's lb algorithm
    updated to hash
    :param persist_config: list of all converted persistence profiles
    :return: Boolean of is pool updated successfully
    """
    pool_updated = True
    pool_obj = [pool for pool in avi_pool_list if pool["name"] == pool_ref]
    if not pool_obj:
        LOG.error("Pool %s not fount to add profile %s" %
                  (pool_ref, persist_profile))
        return False
    pool_obj = pool_obj[0]
    persist_profile_obj = [obj for obj in persist_config
                           if obj["name"] == persist_profile]
    persist_ref_key = "application_persistence_profile_ref"
    if persist_profile_obj:
        pool_obj[persist_ref_key] = persist_profile.replace(' ', '_')
    elif persist_profile == "hash" or persist_profile in hash_profiles:
        del pool_obj["lb_algorithm"]
        hash_algorithm = "LB_ALGORITHM_CONSISTENT_HASH_SOURCE_IP_ADDRESS"
        pool_obj["lb_algorithm_hash"] = hash_algorithm
    else:
        pool_updated = False
    return pool_updated


def update_pool_for_fallback(host, avi_pool_list, pool_ref):
    pool_obj = [pool for pool in avi_pool_list if pool["name"] == pool_ref]
    if pool_obj:
        pool_obj = pool_obj[0]
        fail_action = {
            "redirect":
            {
              "status_code": "HTTP_REDIRECT_STATUS_CODE_302",
              "host": host,
              "protocol": "HTTPS"
            },
            "type": "FAIL_ACTION_HTTP_REDIRECT"
        }
        pool_obj["fail_action"] = fail_action


def add_ssl_to_pool(avi_pool_list, pool_ref, pool_ssl_profiles):
    """
    F5 serverside SSL need to be added to pool if VS contains serverside SSL
    profile this method add that profile to pool
    :param avi_pool_list: List of pools to search pool object
    :param pool_ref: name of the pool
    :param pool_ssl_profiles: ssl profiles to be added to pool
    """
    for pool in avi_pool_list:
        if pool_ref == pool["name"]:
            if pool_ssl_profiles["profile"]:
                pool["ssl_profile_ref"] = pool_ssl_profiles["profile"]
            if pool_ssl_profiles["pki"]:
                pool["pki_profile_ref"] = pool_ssl_profiles["pki"]
            if pool_ssl_profiles["cert"]:
                pool["ssl_key_and_certificate_ref"] = pool_ssl_profiles["cert"]


def get_snat_list_for_vs(snat_pool):
    """
    Converts the f5 snat pool config object to Avi snat list
    :param snat_pool: f5 snat pool config
    :return: Avi snat list
    """
    snat_list = []
    members = snat_pool.get("members")
    ips = members.keys()+members.values()
    if None in ips:
        ips.remove(None)
    for ip in ips:
        snat_obj = {
          "type": "V4",
          "addr": ip
        }
        snat_list.append(snat_obj)
    return snat_list


def convert_vs_config(vs_config, vs_state, avi_pool_list, profile_config,
                      hash_profiles, f5_snat_pools, fallback_host_dict):
    """
    F5 virtual server object conversion to Avi VS object
    :param vs_config: F5 virtual server config list
    :param vs_state: state of new VS to be created in Avi
    :param avi_pool_list: List of pools to handle shared pool scenario
    :param profile_config: Avi profile config for profiles referenced in vs
    :param hash_profiles: Hash profiles handled separately as
    mapped to lb algorithm
    :param f5_snat_pools:
    :return: List of Avi VS configs
    """
    vs_list = []
    supported_attr = ['profiles', 'destination', 'pool', 'persist', 'disabled',
                      'description']
    unsupported_types = ["l2 forward", "ip forward", "stateless", "reject"]
    for vs_name in vs_config.keys():
        LOG.debug("Converting VS: %s" % vs_name)
        try:
            f5_vs = vs_config[vs_name]
            vs_type = [key for key in f5_vs.keys() if key in unsupported_types]
            if vs_type:
                LOG.warn("VS type: %s not supported by Avi skipped VS: %s" %
                          (vs_type, vs_name))
                add_status_row('virtual', None, vs_name, 'skipped')
                continue
            skipped = [key for key in f5_vs.keys() if key not in supported_attr]
            enabled = (vs_state == 'enable')
            vs_profiles = f5_vs.get("profiles", None)
            ssl_vs, ssl_pool, app_prof, ntwk_prof = get_profiles_for_vs(
                vs_profiles, profile_config)
            enable_ssl = False
            if ssl_vs:
                enable_ssl = True
            if enabled:
                enabled = False if "disabled" in f5_vs.keys() else True
            destination = f5_vs["destination"]
            description = f5_vs.get("description", None)
            services_obj, ip_addr = get_service_obj(destination, vs_list,
                                                    enable_ssl)
            pool_ref = f5_vs.get("pool", None)
            if pool_ref:
                shared_vs = [obj for obj in vs_list
                             if obj.get("pool_ref", "") == pool_ref]
                if shared_vs:
                    pool_ref = clone_pool(pool_ref, vs_name, avi_pool_list)
                if ssl_pool:
                    add_ssl_to_pool(avi_pool_list, pool_ref, ssl_pool[0])
                persist_ref = (f5_vs.get("persist", None))
                if persist_ref:
                    persist_config = profile_config.get("persist_profile_list",
                                                        None)
                    pool_updated = update_pool_for_persist(
                        avi_pool_list, pool_ref, persist_ref, hash_profiles,
                        persist_config)
                    if not pool_updated:
                        skipped.append("persist")
                        LOG.warning("persist profile:%s skipped for vs:%s" %
                                    (persist_ref, vs_name))
                if app_prof[0] in fallback_host_dict.keys():
                    host = fallback_host_dict[app_prof[0]]
                    update_pool_for_fallback(host, avi_pool_list, pool_ref)
            vs_obj = {
                'name': vs_name,
                'description': description,
                'type': 'VS_TYPE_NORMAL',
                'ip_address': {
                    'addr': ip_addr,
                    'type': 'V4'
                },
                'enabled': enabled,
                'services': services_obj,
                'application_profile_ref': app_prof[0],
                'pool_ref': pool_ref
            }
            snat = f5_vs.get("snat", 'automap')
            snat = None if snat == 'automap' else snat
            snat_pool = f5_snat_pools.pop(snat, None)
            if snat_pool:
                snat_list = get_snat_list_for_vs(snat_pool)
                vs_obj["snat_ip"] = snat_list
            if ntwk_prof:
                vs_obj['network_profile_ref'] = ntwk_prof[0]
            if enable_ssl:
                vs_obj['ssl_profile_name'] = ssl_vs[0]["profile"]
                if ssl_vs[0]["cert"]:
                    vs_obj['ssl_key_and_certificate_refs'] = [ssl_vs[0]["cert"]]
                if ssl_vs[0]["pki"] and app_prof[0] != "http":
                    app_profiles = [obj for obj in
                                    profile_config["app_profile_list"]
                                    if obj['name'] == app_prof[0]]
                    if app_profiles[0]["type"] == \
                            'APPLICATION_PROFILE_TYPE_HTTP':
                        app_profiles[0]["http_profile"][
                            "ssl_client_certificate_mode"] = \
                            "SSL_CLIENT_CERTIFICATE_REQUEST"
                        app_profiles[0]["http_profile"]["pki_profile_ref"] = \
                            ssl_vs[0]["pki"][0]["name"]
            vs_list.append(vs_obj)
            if skipped:
                add_status_row('virtual', None, vs_name,
                               'partial', skipped, vs_obj)
            else:
                add_status_row('virtual', None, vs_name, 'successful',
                               skipped, vs_obj)
        except:
            LOG.error("Failed to convert VS: %s" % vs_name, exc_info=True)
        LOG.debug("Conversion successful for VS: %s" % vs_name)
    return vs_list


def add_status_row(f5_type, f5_sub_type, f5_id, status, skipped_params=None,
                   avi_object=None, indirect_params=None):
    """
    Adds as status row in conversion status csv
    :param f5_type: Object type
    :param f5_sub_type: Object sub type
    :param f5_id: Name of object
    :param status: conversion status
    :param skipped_params: skipped params if partial conversion
    :param indirect_params: List of attributes have indirect mappings
    :param avi_object: converted avi object
    """
    global csv_writer
    row = {
        'F5 type': f5_type,
        'F5 SubType': f5_sub_type,
        'F5 ID': f5_id,
        'Status': status,
        'Indirect mapping': indirect_params,
        'Skipped settings': str(skipped_params),
        'Avi Object': str(avi_object)
    }
    csv_writer.writerow(row)


def convert_to_avi_dict(f5_config_dict, output_file_path,
                        vs_state, input_folder_location, option):
    """
    Converts f5 config to avi config pops the config lists for conversion of
    each type from f5 config and remaining marked as skipped in the
    conversion status file
    :param f5_config_dict: dict representation of f5 config from the file
    :param output_file_path: Folder path to put output files
    :param vs_state: State of created Avi VS object
    :param input_folder_location: Location of cert and external monitor
    script files
    :param option: Upload option cli-upload or api-upload
    :return: Converted avi objects
    """
    csv_file = open(output_file_path+os.path.sep+"ConversionStatus.csv", 'w')
    global csv_writer
    fieldnames = ['F5 type', 'F5 SubType', 'F5 ID', 'Status',
                  'Skipped settings', 'Indirect mapping', 'Avi Object']
    csv_writer = csv.DictWriter(csv_file, fieldnames=fieldnames,
                                lineterminator='\n',)
    csv_writer.writeheader()
    avi_config_dict = {}
    try:
        monitor_config_list = convert_monitor_config(f5_config_dict.pop(
            "monitor", {}), input_folder_location)
        avi_config_dict["HealthMonitor"] = monitor_config_list
        LOG.debug("Converted health monitors")
        avi_pool_list = convert_pool_config(f5_config_dict.pop("pool", {}),
                                            monitor_config_list)
        avi_config_dict["Pool"] = avi_pool_list
        LOG.debug("Converted pools")
        f5_profile_dict = f5_config_dict.pop("profile", {})
        avi_profiles, string_group, hash_profiles, fallback_host_dict = \
            convert_profile_config(f5_profile_dict, input_folder_location,
                                   option)
        avi_config_dict["SSLKeyAndCertificate"] = \
            avi_profiles["ssl_key_cert_list"]
        update_for_duplicates(avi_config_dict["SSLKeyAndCertificate"])
        avi_config_dict["SSLProfile"] = avi_profiles["ssl_profile_list"]
        update_for_duplicates(avi_config_dict["SSLProfile"])
        avi_config_dict["PKIProfile"] = avi_profiles["pki_profile_list"]
        avi_config_dict["ApplicationProfile"] = avi_profiles["app_profile_list"]
        avi_config_dict["NetworkProfile"] = avi_profiles["network_profile_list"]
        avi_config_dict["ApplicationPersistenceProfile"] = avi_profiles[
            "persist_profile_list"]
        avi_config_dict["StringGroup"] = string_group
        f5_snat_pools = f5_config_dict.get("snatpool", {})
        LOG.debug("Converted ssl profiles")
        avi_vs_list = convert_vs_config(
            f5_config_dict.pop("virtual", {}), vs_state, avi_pool_list,
            avi_profiles, hash_profiles, f5_snat_pools, fallback_host_dict)
        avi_config_dict["VirtualService"] = avi_vs_list
        remove_dup_key(avi_config_dict["SSLKeyAndCertificate"])
        remove_dup_key(avi_config_dict["SSLProfile"])
        LOG.debug("Converted VS")
    except:
        LOG.error("Conversion error", exc_info=True)
    for f5_type in f5_config_dict.keys():
        f5_obj = f5_config_dict[f5_type]
        for key in f5_obj.keys():
            sub_type = None
            if ' ' in key:
                sub_type, key = key.rsplit(' ', 1)
            add_status_row(f5_type, sub_type, key, 'skipped', None, None)
    csv_file.close()
    return avi_config_dict