# ruff: noqa: F403, F405, E402, E501, E722

from fastapi import APIRouter, Request, Response, Depends
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
)
import datetime as dt
from app.jinja2_helpers import *
from app.env import *
from app.state.state import *

from app.classes.Enums import *
from fastapi.encoders import jsonable_encoder
from ccdexplorer_fundamentals.mongodb import MongoDB, MongoTypeInstance
from ccdexplorer_fundamentals.user_v2 import (
    UserV2,
    AccountForUser,
    ContractForUser,
    NotificationPreferences,
    NotificationService,
    AccountNotificationPreferences,
    ContractNotificationPreferences,
    ValidatorNotificationPreferences,
    OtherNotificationPreferences,
)
from typing import Union
from ccdexplorer_fundamentals.tooter import Tooter
from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import *
from pymongo import ReplaceOne


from ccdexplorer_fundamentals.GRPCClient.CCD_Types import *

router = APIRouter()


@router.get("/token/{token}")
async def slash_token(
    request: Request,
    token: str,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    mongodb: MongoDB = Depends(get_mongo_db),
):
    user: UserV2 = get_user_detailsv2(request, token, force=True)
    if not isinstance(user, UserV2):
        user = UserV2(**user)
    if user:
        response = RedirectResponse(url="/settings/user/overview", status_code=303)
        expires = dt.datetime.utcnow() + dt.timedelta(days=30)

        response.set_cookie(
            key="access-token",
            value=token,
            # secure=True,
            # httponly=True,
            expires=expires.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        )
        return response


@router.get("/settings/user/logout")
async def logout(request: Request, response: Response):
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("access-token")
    request.app.user = None
    return response


@router.get("/settings/user/overview")
def user_settings_all(
    request: Request,
    mongodb=Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    user: UserV2 = get_user_detailsv2(request)
    if user:
        if not isinstance(user, UserV2):
            user = UserV2(**user)
        html = generate_edit_html_for_other_notification_preferences(user, mongodb)
    else:
        html = None
    return templates.TemplateResponse(
        "userv2/user_settings_all.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "net": "mainnet",
            "other_notification_preferences": html,
        },
    )


@router.get("/settings/userv2/cancel/email-address")
def cancel_edit_email_address_response(
    request: Request,
    mongodb=Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    user: UserV2 = get_user_detailsv2(request)
    if not isinstance(user, UserV2):
        user = UserV2(**user)
    return templates.TemplateResponse(
        "userv2/user_email_address_start.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "net": "mainnet",
        },
    )


@router.get("/settings/userv2/cancel/other-notification-preferences")
def cancel_edit_other_notification_preferences_response(
    request: Request,
    mongodb=Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    user: UserV2 = get_user_detailsv2(request)
    if not isinstance(user, UserV2):
        user = UserV2(**user)
    return templates.TemplateResponse(
        "userv2/other_notification_preferences_start.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "net": "mainnet",
        },
    )


@router.get("/settings/userv2/cancel/contract/{contract_index}")
def cancel_edit_contract_response(
    request: Request,
    contract_index: int,
    mongodb=Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    user: UserV2 = get_user_detailsv2(request)
    if not isinstance(user, UserV2):
        user = UserV2(**user)
    if not isinstance(user.contracts[str(contract_index)], AccountForUser):
        contract = ContractForUser(**user.contracts[str(contract_index)])
    else:
        contract = user.contracts[str(contract_index)]

    return templates.TemplateResponse(
        "userv2/user_contract_start.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "net": "mainnet",
            "contract": contract,
            "contract_index": contract_index,
        },
    )


@router.get("/settings/userv2/cancel/{account_index}")
def cancel_edit_user_account_response(
    request: Request,
    account_index: CCD_AccountIndex,
    mongodb=Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    user: UserV2 = get_user_detailsv2(request)
    if not isinstance(user, UserV2):
        user = UserV2(**user)
    if not isinstance(user.accounts[str(account_index)], AccountForUser):
        user_account = AccountForUser(**user.accounts[str(account_index)])
    else:
        user_account = user.accounts[str(account_index)]

    return templates.TemplateResponse(
        "userv2/user_account_start.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "net": "mainnet",
            "user_account": user_account,
            "user_account_index": account_index,
        },
    )


@router.put("/settings/userv2/save/email-address", response_class=RedirectResponse)
def save_email_address_response(
    request: Request,
    response_form: dict,
    mongodb=Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    user: UserV2 = get_user_detailsv2(request)
    if not isinstance(user, UserV2):
        user = UserV2(**user)

    response_as_dict = jsonable_encoder(response_form)
    user.email_address = response_as_dict["email_address"]
    user.last_modified = dt.datetime.now().astimezone(tz=dt.timezone.utc)
    # save back to collection
    mongodb.utilities[CollectionsUtilities.users_v2_prod].bulk_write(
        [
            ReplaceOne(
                {"token": str(user.token)},
                user.model_dump(exclude_none=True),
                upsert=True,
            )
        ]
    )
    response = RedirectResponse(url="/settings/user/overview", status_code=204)
    response.headers["HX-Refresh"] = "true"
    return response


@router.put(
    "/settings/userv2/save/new-account",
    response_class=Union[RedirectResponse, HTMLResponse],
)
def save_new_account_response(
    request: Request,
    response_form: dict,
    mongodb=Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    user: UserV2 = get_user_detailsv2(request)
    if not isinstance(user, UserV2):
        user = UserV2(**user)

    user.last_modified = dt.datetime.now().astimezone(tz=dt.timezone.utc)
    response_as_dict = jsonable_encoder(response_form)

    id_or_index: str = response_as_dict["id_or_index"]

    if id_or_index.isnumeric():
        try:
            account_id = grpcclient.get_account_info(
                "last_final", account_index=int(id_or_index)
            ).address
            account_index = id_or_index
            lookup_failed = False
        except:
            lookup_failed = True
    elif not id_or_index.isnumeric():
        try:
            account_index = grpcclient.get_account_info(
                "last_final", hex_address=id_or_index
            ).index
            account_id = id_or_index
            lookup_failed = False
        except:
            lookup_failed = True
    else:
        lookup_failed = True

    if lookup_failed:
        return templates.TemplateResponse(
            "userv2/user_new_account_start.html",
            {
                "env": request.app.env,
                "request": request,
                "user": user,
                "net": "mainnet",
                "error_message": f"You wanted to add address/index: '{id_or_index}'. I have not been able to locate this account on-chain. Please check.",
            },
        )
    else:
        # we now have a valid new account.
        label = response_as_dict.get("label")

        new_account = AccountForUser(
            account_id=account_id, account_index=account_index, label=label
        )
        user.accounts[str(account_index)] = new_account
        # save back to collection
        mongodb.utilities[CollectionsUtilities.users_v2_prod].bulk_write(
            [
                ReplaceOne(
                    {"token": str(user.token)},
                    user.model_dump(exclude_none=True),
                    upsert=True,
                )
            ]
        )
        response = RedirectResponse(url="/settings/user/overview", status_code=204)
        response.headers["HX-Refresh"] = "true"
        return response


class SearchTerm(BaseModel):
    search: int


@router.post(
    "/settings/userv2/search-instance",
    response_class=HTMLResponse,
)
def search_instance_response(
    request: Request,
    response_form: dict,
    mongodb=Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    user: UserV2 = get_user_detailsv2(request)
    if not isinstance(user, UserV2):
        user = UserV2(**user)
    response_as_dict = jsonable_encoder(response_form)
    html = ""
    if response_as_dict["search"].isnumeric():
        _id = f'<{int(response_as_dict["search"])},0>'
        # result = [
        #     MongoTypeInstance(**x)
        #     for x in mongodb.mainnet[Collections.instances].find(
        #         {"_id": {"$regex": response_as_dict["search"]}}
        #     )
        # ]

        # html = "<table class='table'><tbody>"
        # for r in result:
        #     if r.v0:
        #         name = r.v0.name.split("_")[1]
        #     else:
        #         name = r.v1.name.split("_")[1]
        #     html += f"<tr><td><small>{r.id}</td><td><small>{name}</td></tr>"
        # html += "</tbody></table>"

        result = mongodb.mainnet[Collections.instances].find_one({"_id": _id})
        if result:
            r = MongoTypeInstance(**result)
            if r.v0:
                name = r.v0.name.split("_")[1]
            else:
                name = r.v1.name.split("_")[1]
            html = f"<div id='search-results'><span class='small text-muted'><p><small>{r.id} | {name}</small></p></span></div>"
        else:
            html = "<div id='search-results'><span class='small .text-danger '><p><small>Not a valid contract index</small></p></span></div>"
    elif response_as_dict["search"] == "":
        html = "<div id='search-results'><span class='small '><p><small>...</small></p></span></div>"
    else:
        html = "<div id='search-results'><span class='small .text-danger '><p><small>Not a valid contract index</small></p></span></div>"
    return html


@router.put(
    "/settings/userv2/save/new-contract",
    response_class=Union[RedirectResponse, HTMLResponse],
)
def save_new_contract_response(
    request: Request,
    response_form: dict,
    mongodb=Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    user: UserV2 = get_user_detailsv2(request)
    if not isinstance(user, UserV2):
        user = UserV2(**user)

    user.last_modified = dt.datetime.now().astimezone(tz=dt.timezone.utc)
    response_as_dict = jsonable_encoder(response_form)

    contract_index: str = response_as_dict["search"]
    methods = []
    if contract_index.isnumeric():
        try:
            _id = f"<{contract_index},0>"
            result = mongodb.mainnet[Collections.instances].find_one({"_id": _id})
            if result:
                retrieved_instance = MongoTypeInstance(**result)
                if retrieved_instance.v0:
                    name = retrieved_instance.v0.name.split("_")[1]
                    methods = [x.split(".")[1] for x in retrieved_instance.v0.methods]
                else:
                    name = retrieved_instance.v1.name.split("_")[1]
                    methods = [x.split(".")[1] for x in retrieved_instance.v1.methods]
                lookup_failed = False
        except:
            lookup_failed = True
    elif not contract_index.isnumeric():
        lookup_failed = True
    else:
        lookup_failed = True

    if lookup_failed:
        return templates.TemplateResponse(
            "userv2/user_new_contract_start.html",
            {
                "env": request.app.env,
                "request": request,
                "user": user,
                "net": "mainnet",
                "error_message": f"You wanted to add contract index: '{contract_index}'. I have not been able to locate this contract on-chain. Please check.",
            },
        )
    else:
        # we now have a valid new contract.
        label = response_as_dict.get("label")

        new_contract = ContractForUser(
            contract=CCD_ContractAddress.from_str(_id),
            label=label,
            contract_name=name,
            # methods=methods,
        )
        user.contracts[str(contract_index)] = new_contract
        # save back to collection
        mongodb.utilities[CollectionsUtilities.users_v2_prod].bulk_write(
            [
                ReplaceOne(
                    {"token": str(user.token)},
                    user.model_dump(exclude_none=True),
                    upsert=True,
                )
            ]
        )
        response = RedirectResponse(url="/settings/user/overview", status_code=204)
        response.headers["HX-Refresh"] = "true"
        return response


@router.put(
    "/settings/userv2/save/other-notification-preferences", response_class=HTMLResponse
)
def save_other_notification_preferences_response(
    request: Request,
    response_form: dict,
    mongodb=Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    user: UserV2 = get_user_detailsv2(request)
    if not isinstance(user, UserV2):
        user = UserV2(**user)
    user.last_modified = dt.datetime.now().astimezone(tz=dt.timezone.utc)
    other_notification_preferences = user.other_notification_preferences
    if not other_notification_preferences:
        other_notification_preferences = OtherNotificationPreferences()

    response_as_dict = jsonable_encoder(response_form)
    for model_field in OtherNotificationPreferences.model_fields:
        current_notification_preference: NotificationPreferences = (
            other_notification_preferences.__getattribute__(model_field)
        )
        if not current_notification_preference:
            current_notification_preference = NotificationPreferences()

        if response_as_dict.get(f"telegram-{model_field}"):
            # this field is set to enabled in the UI
            telegram_enabled = True
        else:
            # this field is set to non-enabled in the UI
            telegram_enabled = False

        if response_as_dict.get(f"email-{model_field}"):
            # this field is set to enabled in the UI
            email_enabled = True
        else:
            # this field is set to non-enabled in the UI
            email_enabled = False

        if response_as_dict.get(f"telegram-{model_field}-limit"):
            # this field is set to enabled in the UI
            telegram_limit = (
                int(
                    response_as_dict.get(f"telegram-{model_field}-limit")[:-4].replace(
                        ",", ""
                    )
                )
                * 1_000_000
            )
        else:
            # this field is set to non-enabled in the UI
            telegram_limit = None

        if response_as_dict.get(f"email-{model_field}-limit"):
            # this field is set to enabled in the UI
            email_limit = (
                int(
                    response_as_dict.get(f"email-{model_field}-limit")[:-4].replace(
                        ",", ""
                    )
                )
                * 1_000_000
            )
        else:
            # this field is set to non-enabled in the UI
            email_limit = None

        current_notification_preference.telegram = NotificationService(
            enabled=telegram_enabled, limit=telegram_limit
        )
        current_notification_preference.email = NotificationService(
            enabled=email_enabled, limit=email_limit
        )
        other_notification_preferences.__setattr__(
            model_field, current_notification_preference
        )

    # save back to user
    user.other_notification_preferences = other_notification_preferences
    # save back to collection
    mongodb.utilities[CollectionsUtilities.users_v2_prod].bulk_write(
        [
            ReplaceOne(
                {"token": str(user.token)},
                user.model_dump(exclude_none=True),
                upsert=True,
            )
        ]
    )
    response = RedirectResponse(url="/settings/user/overview", status_code=204)
    response.headers["HX-Refresh"] = "true"
    return response


@router.delete(
    "/settings/userv2/delete/{account_index}", response_class=RedirectResponse
)
def delete_user_account_response(
    request: Request,
    account_index: CCD_AccountIndex,
    response: Response,
    mongodb=Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    user: UserV2 = get_user_detailsv2(request)
    if not isinstance(user, UserV2):
        user = UserV2(**user)
    user.last_modified = dt.datetime.now().astimezone(tz=dt.timezone.utc)
    # delete account
    user.accounts.pop(str(account_index))

    # save back to collection
    mongodb.utilities[CollectionsUtilities.users_v2_prod].bulk_write(
        [
            ReplaceOne(
                {"token": str(user.token)},
                user.model_dump(exclude_none=True),
                upsert=True,
            )
        ]
    )

    response = RedirectResponse(url="/settings/user/overview", status_code=204)
    response.headers["HX-Refresh"] = "true"
    return response


@router.delete(
    "/settings/userv2/delete/contract/{contract_index}", response_class=RedirectResponse
)
def delete_contract_response(
    request: Request,
    contract_index: int,
    response: Response,
    mongodb=Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    user: UserV2 = get_user_detailsv2(request)
    if not isinstance(user, UserV2):
        user = UserV2(**user)
    user.last_modified = dt.datetime.now().astimezone(tz=dt.timezone.utc)
    # delete contract
    user.contracts.pop(str(contract_index))

    # save back to collection
    mongodb.utilities[CollectionsUtilities.users_v2_prod].bulk_write(
        [
            ReplaceOne(
                {"token": str(user.token)},
                user.model_dump(exclude_none=True),
                upsert=True,
            )
        ]
    )

    response = RedirectResponse(url="/settings/user/overview", status_code=204)
    response.headers["HX-Refresh"] = "true"
    return response


@router.put(
    "/settings/userv2/save/contract/{contract_index}", response_class=RedirectResponse
)
def save_contract_response(
    request: Request,
    contract_index: int,
    response_form: dict,
    mongodb=Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    response_as_dict = jsonable_encoder(response_form)
    user: UserV2 = get_user_detailsv2(request)
    if not isinstance(user, UserV2):
        user = UserV2(**user)
    if not isinstance(user.contracts[str(contract_index)], AccountForUser):
        contract = ContractForUser(**user.contracts[str(contract_index)])
    else:
        contract = user.contracts[str(contract_index)]

    user.last_modified = dt.datetime.now().astimezone(tz=dt.timezone.utc)

    _id = f"<{contract_index},0>"
    result = mongodb.mainnet[Collections.instances].find_one({"_id": _id})
    methods = []
    if result:
        retrieved_instance = MongoTypeInstance(**result)
        if retrieved_instance.v0:
            methods = [x.split(".")[1] for x in retrieved_instance.v0.methods]
        else:
            methods = [x.split(".")[1] for x in retrieved_instance.v1.methods]

    contract_notification_preferences = contract.contract_notification_preferences
    if not contract_notification_preferences:
        contract_notification_preferences = ContractNotificationPreferences(
            contract_update_issued={}
        )

    for method in methods:
        current_notification_preference: NotificationPreferences = (
            contract_notification_preferences.contract_update_issued.get(method)
        )
        if not current_notification_preference:
            current_notification_preference = NotificationPreferences()

        if response_as_dict.get(f"telegram-{method}"):
            # this field is set to enabled in the UI
            telegram_enabled = True
        else:
            # this field is set to non-enabled in the UI
            telegram_enabled = False

        if response_as_dict.get(f"email-{method}"):
            # this field is set to enabled in the UI
            email_enabled = True
        else:
            # this field is set to non-enabled in the UI
            email_enabled = False

        current_notification_preference.telegram = NotificationService(
            enabled=telegram_enabled
        )
        current_notification_preference.email = NotificationService(
            enabled=email_enabled
        )
        contract_notification_preferences.contract_update_issued[method] = (
            current_notification_preference
        )

    # finally set label
    contract.label = response_as_dict.get("label")
    # save back to user
    contract.contract_notification_preferences = contract_notification_preferences
    user.contracts[str(contract_index)] = contract
    # save back to collection
    mongodb.utilities[CollectionsUtilities.users_v2_prod].bulk_write(
        [
            ReplaceOne(
                {"token": str(user.token)},
                user.model_dump(exclude_none=True),
                upsert=True,
            )
        ]
    )
    # user: UserV2 = get_user_detailsv2(request)
    # if not isinstance(user, UserV2):
    #     user = UserV2(**user)
    # if not isinstance(user.contracts[str(contract_index)], AccountForUser):
    #     contracts = ContractForUser(**user.contracts[str(contract_index)])
    # else:
    #     contracts = user.contracts[str(contract_index)]

    response = RedirectResponse(url="/settings/user/overview", status_code=204)
    response.headers["HX-Refresh"] = "true"
    return response
    # return generate_edit_html_for_user_account(account_index, user, user_account)


@router.put("/settings/userv2/save/{account_index}", response_class=RedirectResponse)
def save_user_account_response(
    request: Request,
    account_index: CCD_AccountIndex,
    response_form: dict,
    mongodb=Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    response_as_dict = jsonable_encoder(response_form)
    user: UserV2 = get_user_detailsv2(request)
    if not isinstance(user, UserV2):
        user = UserV2(**user)
    if not isinstance(user.accounts[str(account_index)], AccountForUser):
        user_account = AccountForUser(**user.accounts[str(account_index)])
    else:
        user_account = user.accounts[str(account_index)]

    user.last_modified = dt.datetime.now().astimezone(tz=dt.timezone.utc)

    # account notification preferences
    account_notification_preferences = user_account.account_notification_preferences
    if not account_notification_preferences:
        account_notification_preferences = AccountNotificationPreferences()

    for model_field in AccountNotificationPreferences.model_fields:
        current_notification_preference: NotificationPreferences = (
            account_notification_preferences.__getattribute__(model_field)
        )
        if not current_notification_preference:
            current_notification_preference = NotificationPreferences()

        if response_as_dict.get(f"telegram-{model_field}"):
            # this field is set to enabled in the UI
            telegram_enabled = True
        else:
            # this field is set to non-enabled in the UI
            telegram_enabled = False

        if response_as_dict.get(f"telegram-{model_field}-limit"):
            # this field is set to enabled in the UI
            telegram_limit = (
                int(
                    response_as_dict.get(f"telegram-{model_field}-limit")[:-4].replace(
                        ",", ""
                    )
                )
                * 1_000_000
            )
        else:
            # this field is set to non-enabled in the UI
            telegram_limit = None

        if response_as_dict.get(f"email-{model_field}"):
            # this field is set to enabled in the UI
            email_enabled = True
        else:
            # this field is set to non-enabled in the UI
            email_enabled = False

        if response_as_dict.get(f"email-{model_field}-limit"):
            # this field is set to enabled in the UI
            email_limit = (
                int(
                    response_as_dict.get(f"email-{model_field}-limit")[:-4].replace(
                        ",", ""
                    )
                )
                * 1_000_000
            )
        else:
            # this field is set to non-enabled in the UI
            email_limit = None

        current_notification_preference.telegram = NotificationService(
            enabled=telegram_enabled, limit=telegram_limit
        )
        current_notification_preference.email = NotificationService(
            enabled=email_enabled, limit=email_limit
        )
        account_notification_preferences.__setattr__(
            model_field, current_notification_preference
        )

    # validator notification preferences
    validator_notification_preferences = user_account.validator_notification_preferences
    if not validator_notification_preferences:
        validator_notification_preferences = ValidatorNotificationPreferences()

    for model_field in ValidatorNotificationPreferences.model_fields:
        current_notification_preference: NotificationPreferences = (
            validator_notification_preferences.__getattribute__(model_field)
        )
        if not current_notification_preference:
            current_notification_preference = NotificationPreferences()

        if response_as_dict.get(f"validator-telegram-{model_field}"):
            # this field is set to enabled in the UI
            telegram_enabled = True
        else:
            # this field is set to non-enabled in the UI
            telegram_enabled = False

        if response_as_dict.get(f"validator-email-{model_field}"):
            # this field is set to enabled in the UI
            email_enabled = True
        else:
            # this field is set to non-enabled in the UI
            email_enabled = False

        current_notification_preference.telegram = NotificationService(
            enabled=telegram_enabled, limit=telegram_limit
        )
        current_notification_preference.email = NotificationService(
            enabled=email_enabled, limit=email_limit
        )
        validator_notification_preferences.__setattr__(
            model_field, current_notification_preference
        )

    # finally set label
    user_account.label = response_as_dict.get("label")
    # save back to user
    user_account.account_notification_preferences = account_notification_preferences
    user_account.validator_notification_preferences = validator_notification_preferences
    user.accounts[str(account_index)] = user_account
    # save back to collection
    mongodb.utilities[CollectionsUtilities.users_v2_prod].bulk_write(
        [
            ReplaceOne(
                {"token": str(user.token)},
                user.model_dump(exclude_none=True),
                upsert=True,
            )
        ]
    )
    user: UserV2 = get_user_detailsv2(request)
    if not isinstance(user, UserV2):
        user = UserV2(**user)
    if not isinstance(user.accounts[str(account_index)], AccountForUser):
        user_account = AccountForUser(**user.accounts[str(account_index)])
    else:
        user_account = user.accounts[str(account_index)]

    response = RedirectResponse(url="/settings/user/overview", status_code=204)
    response.headers["HX-Refresh"] = "true"
    return response
    # return generate_edit_html_for_user_account(account_index, user, user_account)


@router.get("/settings/userv2/edit/email-address", response_class=HTMLResponse)
def edit_email_address(
    request: Request,
    mongodb=Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    user = get_user_detailsv2(request)
    if not isinstance(user, UserV2):
        user = UserV2(**user)

    return generate_edit_html_for_email_address(user)


@router.get(
    "/settings/userv2/edit/other-notification-preferences", response_class=HTMLResponse
)
def edit_other_notification_preferences_response(
    request: Request,
    mongodb=Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    user = get_user_detailsv2(request)
    if isinstance(user, dict):
        user = UserV2(**user)
    if not isinstance(user, UserV2):
        user = UserV2(**user)
    return generate_edit_html_for_other_notification_preferences(user, mongodb)


# note this needs to be below the other-notification-preferences route,
# as the order matters! 422 otherwise..
@router.get("/settings/userv2/edit/{account_index}", response_class=HTMLResponse)
def edit_user_account_response(
    request: Request,
    account_index: CCD_AccountIndex,
    mongodb=Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    user = get_user_detailsv2(request)
    if isinstance(user, dict):
        user = UserV2(**user)
    if not isinstance(user, UserV2):
        user = UserV2(**user)
    user_account = AccountForUser(**user.accounts[str(account_index)])

    return generate_edit_html_for_user_account(
        account_index, user, user_account, grpcclient, mongodb
    )


@router.get(
    "/settings/userv2/edit/contract/{contract_index}", response_class=HTMLResponse
)
def edit_contract_response(
    request: Request,
    contract_index: int,
    mongodb=Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    user = get_user_detailsv2(request)
    if isinstance(user, dict):
        user = UserV2(**user)
    if not isinstance(user, UserV2):
        user = UserV2(**user)
    contract = ContractForUser(**user.contracts[str(contract_index)])
    _id = f"<{contract_index},0>"
    result = mongodb.mainnet[Collections.instances].find_one({"_id": _id})
    methods = []
    if result:
        retrieved_instance = MongoTypeInstance(**result)
        if retrieved_instance.v0:
            methods = [x.split(".")[1] for x in retrieved_instance.v0.methods]
        else:
            methods = [x.split(".")[1] for x in retrieved_instance.v1.methods]

    return generate_edit_html_for_contract(
        contract_index, user, contract, methods, grpcclient, mongodb
    )


def generate_edit_html_for_contract(
    contract_index: int,
    user: UserV2,
    contract: ContractForUser,
    methods: list[str],
    grpcclient: GRPCClient,
    mongodb: MongoDB,
):
    result = mongodb.utilities[CollectionsUtilities.preferences_explanations].find({})
    explanations = {x["_id"]: x for x in result}
    html = f"""
<form hx-put="/settings/userv2/save/contract/{contract_index}" hx-ext='json-enc' hx-target="this" >
  """

    contract_all_fields = methods
    contract_all_fields_dict = {}
    if not contract.contract_notification_preferences:
        contract.contract_notification_preferences = ContractNotificationPreferences(
            contract_update_issued={}
        )
    cui: dict = contract.contract_notification_preferences.contract_update_issued
    for method in contract_all_fields:
        if cui.get(method):
            pass
            # notification_field = (
            #     contract.contract_notification_preferences.__getattribute__(method)
            # )
            if cui[method].__getattribute__("telegram"):
                telegram_notification = cui[method].__getattribute__("telegram")
                try:
                    telegram_enabled = telegram_notification.__getattribute__("enabled")
                except:
                    telegram_enabled = False

            if cui[method].__getattribute__("email"):
                email_notification = cui[method].__getattribute__("telegram")
                try:
                    email_enabled = email_notification.__getattribute__("email")
                except:
                    email_enabled = False

            contract_all_fields_dict[method] = {
                "telegram_enabled": telegram_enabled,
                "telegram_limit": None,
                "email_enabled": email_enabled,
                "email_limit": None,
            }
        else:
            contract_all_fields_dict[method] = {
                "telegram_enabled": False,
                "telegram_limit": None,
                "email_enabled": False,
                "email_limit": None,
            }

    html += templates.get_template("/userv2/contract.html").render(
        {
            "contract_all_fields": contract_all_fields,
            "contract_all_fields_dict": contract_all_fields_dict,
            "contract_notification_preferences": contract.contract_notification_preferences,
            "contract": contract,
            "user": user,
            "explanations": explanations,
        }
    )

    html += f"""
    <div class="row">
  <div class="col">
    <button class="btn small ms-1 mt-0 btn-sm btn-link">Save</button>
  </div>
  <div class="col">
    <button class="btn small ms-1 mt-0 btn-sm btn-link" hx-get="/settings/userv2/cancel/contract/{contract_index}" x-ext='json-enc' >Cancel</button>
  </div>
  <div class="col">
    <button class="btn small ms-1 mt-0 btn-sm btn-link btn-danger" hx-confirm="Are you sure you wish to delete this contract?" hx-delete="/settings/userv2/delete/contract/{contract_index}" x-ext='json-enc' >Delete</button>
  </div>
</div>
    </form>
    
    """
    return html


def generate_edit_html_for_user_account(
    account_index: CCD_AccountIndex,
    user: UserV2,
    user_account: AccountForUser,
    grpcclient: GRPCClient,
    mongodb: MongoDB,
):
    result = mongodb.utilities[CollectionsUtilities.preferences_explanations].find({})
    explanations = {x["_id"]: x for x in result}
    html = f"""
<form hx-put="/settings/userv2/save/{account_index}" hx-ext='json-enc' hx-target="this" >
  """
    account_all_fields = AccountNotificationPreferences.model_fields
    account_all_fields_dict = {}
    for field in account_all_fields:
        if not user_account.account_notification_preferences:
            user_account.account_notification_preferences = (
                AccountNotificationPreferences()
            )
        if user_account.account_notification_preferences.__getattribute__(field):
            notification_field = (
                user_account.account_notification_preferences.__getattribute__(field)
            )
            if notification_field.__getattribute__("telegram"):
                telegram_notification = notification_field.__getattribute__("telegram")
                try:
                    telegram_enabled = telegram_notification.__getattribute__("enabled")
                except:
                    telegram_enabled = False
                try:
                    telegram_limit = telegram_notification.__getattribute__("limit")
                except:
                    telegram_limit = None

                email_notification = notification_field.__getattribute__("email")
                try:
                    email_enabled = email_notification.__getattribute__("enabled")
                except:
                    email_enabled = False
                try:
                    email_limit = email_notification.__getattribute__("limit")
                except:
                    email_limit = None

                account_all_fields_dict[field] = {
                    "telegram_enabled": telegram_enabled,
                    "telegram_limit": telegram_limit,
                    "email_enabled": email_enabled,
                    "email_limit": email_limit,
                }
        else:
            account_all_fields_dict[field] = {
                "telegram_enabled": False,
                "telegram_limit": None,
                "email_enabled": False,
                "email_limit": None,
            }

    # we need to check if this account is a validator, otherwise, don't show validator preferences.
    account_info = grpcclient.get_account_info(
        "last_final", account_index=account_index
    )

    validator_all_fields = ValidatorNotificationPreferences.model_fields
    validator_all_fields_dict = {}
    if account_info.stake.baker:
        for field in validator_all_fields:
            if not user_account.validator_notification_preferences:
                user_account.validator_notification_preferences = (
                    ValidatorNotificationPreferences()
                )
            if user_account.validator_notification_preferences.__getattribute__(field):
                notification_field = (
                    user_account.validator_notification_preferences.__getattribute__(
                        field
                    )
                )
                if notification_field.__getattribute__("telegram"):
                    telegram_notification = notification_field.__getattribute__(
                        "telegram"
                    )
                    try:
                        telegram_enabled = telegram_notification.__getattribute__(
                            "enabled"
                        )
                    except:
                        telegram_enabled = False

                    email_notification = notification_field.__getattribute__("email")
                    try:
                        email_enabled = email_notification.__getattribute__("enabled")
                    except:
                        email_enabled = False

                    validator_all_fields_dict[field] = {
                        "telegram_enabled": telegram_enabled,
                        "telegram_limit": None,
                        "email_enabled": email_enabled,
                        "email_limit": None,
                    }
            else:
                validator_all_fields_dict[field] = {
                    "telegram_enabled": False,
                    "telegram_limit": None,
                    "email_enabled": False,
                    "email_limit": None,
                }

    html += templates.get_template("/userv2/user_account.html").render(
        {
            "account_all_fields": account_all_fields,
            "account_all_fields_dict": account_all_fields_dict,
            "validator_all_fields": validator_all_fields,
            "validator_all_fields_dict": validator_all_fields_dict,
            "account_notification_preferences": user_account.account_notification_preferences,
            "validator_notification_preferences": user_account.validator_notification_preferences,
            "user_account": user_account,
            "user": user,
            "explanations": explanations,
        }
    )

    html += f"""
    <div class="row">
  <div class="col">
    <button class="btn small ms-1 mt-0 btn-sm btn-link">Save</button>
  </div>
  <div class="col">
    <button class="btn small ms-1 mt-0 btn-sm btn-link" hx-get="/settings/userv2/cancel/{account_index}" x-ext='json-enc' >Cancel</button>
  </div>
  <div class="col">
    <button class="btn small ms-1 mt-0 btn-sm btn-link btn-danger" hx-confirm="Are you sure you wish to delete this account?" hx-delete="/settings/userv2/delete/{account_index}" x-ext='json-enc' >Delete</button>
  </div>
</div>
    </form>
    
    """
    return html


def generate_edit_html_for_other_notification_preferences(
    user: UserV2, mongodb: MongoDB
):
    result = mongodb.utilities[CollectionsUtilities.preferences_explanations].find({})
    explanations = {x["_id"]: x for x in result}
    html = """
<form hx-put="/settings/userv2/save/other-notification-preferences" hx-ext='json-enc' hx-target="this" hx-swap="outerHTML">
  """
    all_fields = OtherNotificationPreferences.model_fields
    all_fields_dict = {}
    if not isinstance(user, UserV2):
        user = UserV2(**user)
    for field in all_fields:
        if not user.other_notification_preferences:
            user.other_notification_preferences = OtherNotificationPreferences()
        if user.other_notification_preferences.__getattribute__(field):
            notification_field = user.other_notification_preferences.__getattribute__(
                field
            )
            if notification_field.__getattribute__("telegram"):
                telegram_notification = notification_field.__getattribute__("telegram")
                telegram_enabled = telegram_notification.__getattribute__("enabled")
                try:
                    telegram_limit = telegram_notification.__getattribute__("limit")
                except:
                    pass

                email_notification = notification_field.__getattribute__("email")

                try:
                    email_enabled = email_notification.__getattribute__("enabled")
                    email_limit = email_notification.__getattribute__("limit")
                except:
                    email_enabled = False
                    email_limit = None

                all_fields_dict[field] = {
                    "telegram_enabled": telegram_enabled,
                    "telegram_limit": telegram_limit,
                    "email_enabled": email_enabled,
                    "email_limit": email_limit,
                }
        else:
            all_fields_dict[field] = {
                "telegram_enabled": False,
                "telegram_limit": None,
                "email_enabled": False,
                "email_limit": None,
            }

    html += templates.get_template(
        "/userv2/other_notification_preferences.html"
    ).render(
        {
            "all_fields": all_fields,
            "all_fields_dict": all_fields_dict,
            "other_notification_preferences": user.other_notification_preferences,
            "user": user,
            "explanations": explanations,
        }
    )

    html += """
    <div class="row">
  <div class="col">
    <button class="btn small ms-1 mt-0 btn-sm btn-link">Save</button>
    <button class="btn small ms-1 mt-0 btn-sm btn-link" hx-get="/settings/userv2/cancel/other-notification-preferences" x-ext='json-enc' >Cancel</button>
  </div>
</div>
    </form>
    """
    return html


def generate_edit_html_for_email_address(user: UserV2):
    html = """
<form hx-put="/settings/userv2/save/email-address" hx-ext='json-enc' hx-target="this" hx-swap="outerHTML">
  """

    html += templates.get_template("/userv2/user_email_address.html").render(
        {
            "user": user,
        }
    )

    html += """
    <div class="row">
  <div class="col">
    <button class="btn small ms-1 mt-0 btn-sm btn-link">Save</button>
    <button class="btn small ms-1 mt-0 btn-sm btn-link" hx-get="/settings/userv2/cancel/email-address" x-ext='json-enc' >Cancel</button>
  </div>
</div>
    </form>
    """
    return html
