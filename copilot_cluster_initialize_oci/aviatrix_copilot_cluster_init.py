import json
import logging
import sys
import time
import traceback
import requests
import uuid
from multiprocessing import Process

import oci


class AviatrixException(Exception):
    def __init__(self, message="Aviatrix Error Message: ..."):
        super(AviatrixException, self).__init__(message)


def add_ingress_rules(
        user_id,
        tenancy_id,
        fingerprint,
        key_file,
        region,
        rule,
        nsg_id
):
    config = {
        "user": user_id,
        "key_file": key_file,
        "fingerprint": fingerprint,
        "tenancy": tenancy_id,
        "region": region
    }

    virtual_network_client = oci.core.VirtualNetworkClient(config)

    # rule = oci.core.models.AddSecurityRuleDetails(
    #     description="Incoming Internet connections",
    #     direction="INGRESS",
    #     is_stateless=False,
    #     protocol="6",  # 1: ICMP, 6: TCP, 17: UDP, 58: ICMPv6
    #     source="0.0.0.0/0",
    #     source_type="CIDR_BLOCK",
    #     tcp_options=oci.core.models.TcpOptions(destination_port_range=oci.core.models.PortRange(min=443, max=443))
    # )

    # nsg_id = "ocid1.networksecuritygroup.oc1.iad.aaaaaaaactomf3c3l5fc65dmr5ix4ud44zzntl7lexg75dl3ejck3f3lysra"

    virtual_network_client.add_network_security_group_security_rules(
        nsg_id,
        oci.core.models.AddNetworkSecurityGroupSecurityRulesDetails(security_rules=[rule])
    )


def send_aviatrix_api(
        api_endpoint_url="https://123.123.123.123/v1/api",
        request_method="POST",
        payload=dict(),
        headers=dict(),
        retry_count=5,
        sleep_between_retries=0,
        timeout=None,
        files=dict(),
):
    response = None
    responses = list()
    request_type = request_method.upper()
    response_status_code = -1

    for i in range(retry_count):
        try:
            if request_type == "GET":
                response = requests.get(
                    url=api_endpoint_url, params=payload, headers=headers, verify=False
                )
                response_status_code = response.status_code
            elif request_type == "POST":
                response = requests.post(
                    url=api_endpoint_url, data=payload, headers=headers, verify=False, timeout=timeout, files=files
                )
                response_status_code = response.status_code
            else:
                failure_reason = "ERROR : Bad HTTPS request type: " + request_type
                logging.error(failure_reason)
        except requests.exceptions.Timeout as e:
            logging.exception("WARNING: Request timeout...")
            responses.append(str(e))
        except requests.exceptions.ConnectionError as e:
            logging.exception("WARNING: Server is not responding...")
            responses.append(str(e))
        except Exception as e:
            traceback_msg = traceback.format_exc()
            logging.exception("HTTP request failed")
            responses.append(str(traceback_msg))

        finally:
            if response_status_code == 200:
                return response
            elif response_status_code == 404:
                failure_reason = "ERROR: 404 Not Found"
                logging.error(failure_reason)
            else:
                return response

            # if the response code is neither 200 nor 404, repeat the precess (retry)

            if i + 1 < retry_count:
                logging.info("START: retry")
                logging.info("i == %d", i)
                logging.info("Wait for: %ds for the next retry", sleep_between_retries)
                time.sleep(sleep_between_retries)
                logging.info("ENDED: Wait until retry")
                # continue next iteration
            else:
                failure_reason = (
                        "ERROR: Failed to invoke API at " + api_endpoint_url + ". Exceed the max retry times. "
                        + " All responses are listed as follows :  "
                        + str(responses)
                )
                raise AviatrixException(
                    message=failure_reason,
                )

    return response


def login_controller(
        controller_ip,
        username,
        password,
        hide_password=True,
):
    request_method = "POST"
    data = {
        "action": "login",
        "username": username,
        "password": password
    }

    api_endpoint_url = "https://" + controller_ip + "/v1/api"
    logging.info("API endpoint url is : %s", api_endpoint_url)

    # handle if the hide_password is selected
    if hide_password:
        payload_with_hidden_password = dict(data)
        payload_with_hidden_password["password"] = "************"
        logging.info(
            "Request payload: %s",
            str(json.dumps(obj=payload_with_hidden_password, indent=4)),
        )
    else:
        logging.info("Request payload: %s", str(json.dumps(obj=data, indent=4)))

    # send post request to the api endpoint
    response = send_aviatrix_api(
        api_endpoint_url=api_endpoint_url,
        request_method=request_method,
        payload=data,
        retry_count=12,
        sleep_between_retries=10
    )

    return response


def verify_controller_login_response(response=None):
    # if successfully login
    # response_code == 200
    # api_return_boolean == true
    # response_message = "authorized successfully"

    py_dict = response.json()
    logging.info("Aviatrix API response is %s", str(py_dict))

    response_code = response.status_code
    if response_code != 200:
        err_msg = (
                "Fail to login Aviatrix Controller. The response code is" + response_code
        )
        raise AviatrixException(message=err_msg)

    api_return_boolean = py_dict["return"]
    if api_return_boolean is not True:
        err_msg = "Fail to Login Aviatrix Controller. The Response is" + str(py_dict)
        raise AviatrixException(
            message=err_msg,
        )

    api_return_msg = py_dict["results"]
    expected_string = "authorized successfully"
    if (expected_string in api_return_msg) is not True:
        err_msg = "Fail to Login Aviatrix Controller. The Response is" + str(py_dict)
        raise AviatrixException(
            message=err_msg,
        )


def login_copilot(
        controller_ip,
        copilot_ip,
        username,
        password,
        hide_password=True,
):
    request_method = "POST"
    data = {
        "controllerIp": controller_ip,
        "username": username,
        "password": password
    }

    api_endpoint_url = "https://" + copilot_ip + "/login"
    logging.info("API endpoint url is : %s", api_endpoint_url)

    # handle if the hide_password is selected
    if hide_password:
        payload_with_hidden_password = dict(data)
        payload_with_hidden_password["password"] = "************"
        logging.info(
            "Request payload: %s",
            str(json.dumps(obj=payload_with_hidden_password, indent=4)),
        )
    else:
        logging.info("Request payload: %s", str(json.dumps(obj=data, indent=4)))

    # send post request to the api endpoint
    response = send_aviatrix_api(
        api_endpoint_url=api_endpoint_url,
        request_method=request_method,
        payload=data,
        retry_count=12,
        sleep_between_retries=10
    )

    return response


def copilot_login_driver(controller_ip, login_info):
    processes = [Process(target=login_copilot, args=(controller_ip, copilot_ip, username, password))
                 for copilot_ip, username, password in login_info]

    for p in processes:
        p.start()

    for p in processes:
        p.join()


def init_copilot_cluster(
        controller_username,
        controller_password,
        main_copilot_ip,
        init_info,
        CID,
        hide_password=True
):
    request_method = "POST"
    headers = {
        "content-type": "application/json",
        "cid": CID
    }

    cluster_db = []
    for private_ip, name in init_info:
        cluster = {
            "physicalVolumes": [],
            "clusterNodeName": name,
            "clusterNodeEIP": private_ip,
            "clusterNodeInterIp": private_ip,
            "clusterUUID": str(uuid.uuid4())
        }
        cluster_db.append(cluster)

    data = {
        "copilotType": "mainCopilot",
        "mainCopilotIp": main_copilot_ip,
        "clusterDB": cluster_db,
        "taskserver": {
            "username": controller_username,
            "password": controller_password
        }
    }

    api_endpoint_url = "https://" + main_copilot_ip + "/v1/api/cluster"
    logging.info("API endpoint url is : %s", api_endpoint_url)

    # handle if the hide_password is selected
    if hide_password:
        payload_with_hidden_password = dict(data)
        payload_with_hidden_password["taskserver"]["password"] = "************"
        logging.info(
            "Request payload: %s",
            str(json.dumps(obj=payload_with_hidden_password, indent=4)),
        )
        data["taskserver"]["password"] = controller_password
    else:
        logging.info("Request payload: %s", str(json.dumps(obj=data, indent=4)))

    # send post request to the api endpoint
    response = send_aviatrix_api(
        api_endpoint_url=api_endpoint_url,
        request_method=request_method,
        payload=json.dumps(data),
        headers=headers
    )

    return response


def get_copilot_init_status(
        main_copilot_ip,
        CID,
):
    request_method = "GET"
    headers = {
        "content-type": "application/json",
        "cid": CID
    }

    api_endpoint_url = "https://" + main_copilot_ip + "/v1/api/cluster"
    logging.info("API endpoint url is : %s", api_endpoint_url)

    # send get request to the api endpoint
    response = send_aviatrix_api(
        api_endpoint_url=api_endpoint_url,
        request_method=request_method,
        headers=headers,
    )

    return response


def function_handler(event):
    user_id = event["user_id"]
    tenancy_id = event["tenancy_id"]
    fingerprint = event["fingerprint"]
    key_file = event["key_file"]
    region = event["region"]

    controller_public_ip = event["controller_public_ip"]
    controller_private_ip = event["controller_private_ip"]
    controller_username = event["controller_username"]
    controller_password = event["controller_password"]
    controller_nsg_id = event["controller_nsg_id"]

    main_copilot_public_ip = event["main_copilot_public_ip"]
    main_copilot_private_ip = event["main_copilot_private_ip"]
    main_copilot_username = event["main_copilot_username"]
    main_copilot_password = event["main_copilot_password"]
    main_copilot_nsg_id = event["main_copilot_nsg"]

    node_copilot_public_ips = event["node_copilot_public_ips"]
    node_copilot_private_ips = event["node_copilot_private_ips"]
    node_copilot_usernames = event["node_copilot_usernames"]
    node_copilot_passwords = event["node_copilot_passwords"]
    node_copilot_names = event["node_copilot_names"]
    node_copilot_nsg_ids = event["node_copilot_nsg_ids"]


    # private_mode = event["private_mode"]

    # controller_login_ip = controller_private_ip if private_mode else controller_public_ip
    # main_copilot_login_ip = main_copilot_private_ip if private_mode else main_copilot_public_ip

    controller_login_ip = controller_public_ip
    main_copilot_login_ip = main_copilot_public_ip

    # login_info = zip([main_copilot_private_ip] + node_copilot_private_ips,
    #                  [main_copilot_username] + node_copilot_usernames,
    #                  [main_copilot_password] + node_copilot_passwords) if private_mode else \

    login_info = zip([main_copilot_public_ip] + node_copilot_public_ips,
                     [main_copilot_username] + node_copilot_usernames,
                     [main_copilot_password] + node_copilot_passwords)

    init_info = zip(node_copilot_private_ips, node_copilot_names)

    all_copilot_public_ips = [main_copilot_public_ip] + node_copilot_public_ips
    all_copilot_private_ips = [main_copilot_private_ip] + node_copilot_private_ips
    all_copilot_nsg_ids = [main_copilot_nsg_id] + node_copilot_nsg_ids

    ###########################################################################
    # Step 1: Modify the security groups for controller and copilot instances #
    ###########################################################################
    logging.info("STEP 1 START: Modify the security groups for controller and copilot instances.")

    # modify controller security rule

    for ip in all_copilot_public_ips:
        rule = oci.core.models.AddSecurityRuleDetails(
            description="Incoming Internet connections",
            direction="INGRESS",
            is_stateless=False,
            protocol="6",  # 1: ICMP, 6: TCP, 17: UDP, 58: ICMPv6
            source=ip + "/32",
            source_type="CIDR_BLOCK",
            tcp_options=oci.core.models.TcpOptions(destination_port_range=oci.core.models.PortRange(min=443, max=443))
        )
        add_ingress_rules(user_id, tenancy_id, fingerprint, key_file, region, rule, controller_nsg_id)

    # modify copilot security rule
    copilot_allowed_cidrs = []

    for i in all_copilot_nsg_ids:
        for ip in all_copilot_public_ips:
            rule = oci.core.models.AddSecurityRuleDetails(
                description="Incoming Internet connections",
                direction="INGRESS",
                is_stateless=False,
                protocol="6",  # 1: ICMP, 6: TCP, 17: UDP, 58: ICMPv6
                source=ip + "/32",
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.models.TcpOptions(destination_port_range=oci.core.models.PortRange(min=443, max=443))
            )
            add_ingress_rules(user_id, tenancy_id, fingerprint, key_file, region, rule, all_copilot_nsg_ids[i])

        for ip in all_copilot_private_ips:
            rule = oci.core.models.AddSecurityRuleDetails(
                description="Incoming Internet connections",
                direction="INGRESS",
                is_stateless=False,
                protocol="6",  # 1: ICMP, 6: TCP, 17: UDP, 58: ICMPv6
                source=ip + "/32",
                source_type="CIDR_BLOCK",
                tcp_options=oci.core.models.TcpOptions(destination_port_range=oci.core.models.PortRange(min=443, max=443))
            )
            add_ingress_rules(user_id, tenancy_id, fingerprint, key_file, region, rule, all_copilot_nsg_ids[i])

    # logging.info(copilot_rules)

    logging.info("STEP 1 ENDED: Modified the security groups for controller and copilot instances.")

    ###################################
    # Step 2: Try to login controller #
    ###################################
    logging.info("STEP 2 START: Login controller.")

    response = login_controller(
        controller_ip=controller_login_ip,
        username=controller_username,
        password=controller_password
    )

    verify_controller_login_response(response=response)

    logging.info("STEP 2 ENDED: Logged into controller.")

    #################################################################################
    # Step 3: Try to login main copilot and cluster nodes. Retry every 10s for 2min #
    #################################################################################
    logging.info("STEP 3 START: Try to login main copilot and cluster nodes. Retry every 10s for 2min.")

    copilot_login_driver(controller_ip=controller_login_ip, login_info=login_info)

    logging.info("STEP 3 ENDED: Logged into main copilot and cluster nodes.")

    #######################################
    # Step 4: Login controller to get CID #
    #######################################
    logging.info("STEP 4 START: Login controller to get CID.")

    response = login_controller(
        controller_ip=controller_login_ip,
        username=controller_username,
        password=controller_password
    )

    verify_controller_login_response(response=response)
    CID = response.json()["CID"]

    logging.info("STEP 4 ENDED: Logged into controller and got CID.")

    ##################################################
    # Step 5: Call API to initialize copilot cluster #
    ##################################################
    logging.info("STEP 5 START: Call API to initialize copilot cluster.")

    response = init_copilot_cluster(
        controller_username=controller_username,
        controller_password=controller_password,
        main_copilot_ip=main_copilot_login_ip,
        init_info=init_info,
        CID=CID
    )

    if response.status_code != 200:
        raise AviatrixException(message="Initialization API call failed")

    logging.info("STEP 5 ENDED: Called API to initialize copilot cluster.")

    #######################################
    # Step 6: Check initialization status #
    #######################################
    logging.info("STEP 6 START: Check initialization status.")

    retry_count = 30
    sleep_between_retries = 30

    for i in range(retry_count):
        response = get_copilot_init_status(
            main_copilot_ip=main_copilot_login_ip,
            CID=CID
        )

        py_dict = response.json()
        api_return_msg = py_dict.get("status")
        logging.info(py_dict.get("message"))

        if api_return_msg == "failed":
            raise AviatrixException(message="Initialization failed.")
        elif api_return_msg == "done":
            return

        if i + 1 < retry_count:
            logging.info("START: retry")
            logging.info("i == %d", i)
            logging.info("Wait for: %ds for the next retry", sleep_between_retries)
            time.sleep(sleep_between_retries)
            logging.info("ENDED: Wait until retry")
            # continue next iteration
        else:
            raise AviatrixException(
                message="Exceed the max retry times. Initialization still not done.",
            )

    logging.info("STEP 6 ENDED: Initialization status check is done.")


if __name__ == '__main__':
    logging.basicConfig(
        format="%(asctime)s copilot-cluster-init--- %(message)s", level=logging.INFO
    )

    i = 1
    user_id = sys.argv[i]
    i += 1
    tenancy_id = sys.argv[i]
    i += 1
    fingerprint = sys.argv[i]
    i += 1
    key_file = sys.argv[i]
    i += 1
    region = sys.argv[i]
    i += 1
    controller_public_ip = sys.argv[i]
    i += 1
    controller_private_ip = sys.argv[i]
    i += 1
    controller_username = sys.argv[i]
    i += 1
    controller_password = sys.argv[i]
    i += 1
    controller_nsg_id = sys.argv[i]
    i += 1
    main_copilot_public_ip = sys.argv[i]
    i += 1
    main_copilot_private_ip = sys.argv[i]
    i += 1
    main_copilot_username = sys.argv[i]
    i += 1
    main_copilot_password = sys.argv[i]
    i += 1
    main_copilot_nsg_id = sys.argv[i]
    i += 1
    node_copilot_public_ips = sys.argv[i].split(",")
    i += 1
    node_copilot_private_ips = sys.argv[i].split(",")
    i += 1
    node_copilot_usernames = sys.argv[i].split(",")
    i += 1
    node_copilot_passwords = sys.argv[i].split(",")
    i += 1
    node_copilot_names = sys.argv[i].split(",")
    i += 1
    node_copilot_nsg_ids = sys.argv[i].split(",")

    event = {
        "user_id": user_id,
        "tenancy_id": tenancy_id,
        "fingerprint": fingerprint,
        "key_file": key_file,
        "region": region,
        "controller_public_ip": controller_public_ip,
        "controller_private_ip": controller_private_ip,
        "controller_username": controller_username,
        "controller_password": controller_password,
        "controller_nsg_id": controller_nsg_id,
        "main_copilot_public_ip": main_copilot_public_ip,
        "main_copilot_private_ip": main_copilot_private_ip,
        "main_copilot_username": main_copilot_username,
        "main_copilot_password": main_copilot_password,
        "main_copilot_nsg_id": main_copilot_nsg_id,
        "node_copilot_public_ips": node_copilot_public_ips,
        "node_copilot_private_ips": node_copilot_private_ips,
        "node_copilot_usernames": node_copilot_usernames,
        "node_copilot_passwords": node_copilot_passwords,
        "node_copilot_names": node_copilot_names,
        "node_copilot_nsg_ids": node_copilot_nsg_ids,
    }

    try:
        function_handler(event)
    except Exception as e:
        logging.exception("")
    else:
        logging.info("Aviatrix Copilot Cluster has been initialized successfully.")
