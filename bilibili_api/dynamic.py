"""
bilibili_api.dynamic

动态相关
"""

import json
import re
import os
from typing import Any, List, Tuple, Union, Optional
from enum import Enum

from .exceptions.DynamicExceedImagesException import DynamicExceedImagesException
from .utils.network_httpx import request
from .utils.Credential import Credential
from .utils.sync import sync
from . import user, exceptions
from .utils import utils
from .utils.Picture import Picture
from .vote import Vote
from .user import User
from .topic import Topic

API = utils.get_api("dynamic")


class DynamicType(Enum):
    """
    动态类型

    + ALL: 所有动态
    + ANIME: 追番追剧
    + ARTICLE: 文章
    + VIDEO: 视频投稿
    """
    ALL = "all"
    ANIME = "pgc"
    ARTICLE = "article"
    VIDEO = "video"


class SendDynmaicType(Enum):
    """
    发送动态类型
    scene 参数

    + TEXT: 纯文本
    + IMAGE: 图片
    """
    TEXT = 1
    IMAGE = 2


class DynmaicContentType(Enum):
    """
    动态内容类型

    + TEXT: 文本
    + EMOJI: 表情
    + AT: @User
    + VOTE: 投票
    """
    TEXT = 1
    EMOJI = 9
    AT = 2
    VOTE = 4


async def _parse_at(text: str) -> Tuple[str, str, str]:
    """
    @人格式：“@用户名 ”(注意最后有空格）

    Args:
        text (str): 原始文本

    Returns:
        tuple(str, str(int[]), str(dict)): 替换后文本，解析出艾特的 UID 列表，AT 数据
    """
    text += " "
    pattern = re.compile(r"(?<=@).*?(?=\s)")
    match_result = re.finditer(pattern, text)
    uid_list = []
    names = []
    new_text = text
    for match in match_result:
        uname = match.group()
        try:
            uid = (await user.name2uid(uname))["uid_list"][0]["uid"]
        except KeyError:
            # 没有此用户
            continue

        u = user.User(int(uid))
        user_info = await u.get_user_info()

        name = user_info["name"]
        uid_list.append(str(uid))
        names.append(name)
        new_text = new_text.replace(f"@{uid} ", f"@{name} ")
    at_uids = ",".join(uid_list)
    ctrl = []

    for i, name in enumerate(names):
        index = new_text.index(f"@{name}")
        length = 2 + len(name)
        ctrl.append(
            {"location": index, "type": 1,
                "length": length, "data": int(uid_list[i])}
        )

    return new_text, at_uids, json.dumps(ctrl, ensure_ascii=False)


async def _get_text_data(text: str) -> dict:
    """
    获取文本动态请求参数

    Args:
        text (str): 文本内容

    Returns:
        dict: 文本动态请求数据
    """
    new_text, at_uids, ctrl = await _parse_at(text)
    data = {
        "dynamic_id": 0,
        "type": 4,
        "rid": 0,
        "content": new_text,
        "extension": '{"emoji_type":1}',
        "at_uids": at_uids,
        "ctrl": ctrl,
    }
    return data


async def upload_image(image: Picture, credential: Credential) -> dict:
    """
    上传动态图片

    Args:
        image        (Picture)   : 图片流. 有格式要求.
        credential   (Credential): 凭据

    Returns:
        dict: 调用 API 返回的结果
    """
    credential.raise_for_no_sessdata()
    credential.raise_for_no_bili_jct()

    api = API["send"]["upload_img"]
    raw = image.content

    data = {"biz": "new_dyn", "category": "daily"}

    return_info = await request(
        "POST",
        url=api["url"],
        data=data,
        files={"file_up": raw},
        credential=credential,
    )

    return return_info

class Dynamic:
    """
    动态类

    Attributes:
        credential (Credential): 凭据类
    """

    def __init__(self, dynamic_id: int, credential: Union[Credential, None] = None) -> None:
        """
        Args:
            dynamic_id (int)                        : 动态 ID
            credential (Credential | None, optional): 凭据类. Defaults to None.
        """
        self.__dynamic_id = dynamic_id
        self.credential = credential if credential is not None else Credential()

    def get_dynamic_id(self) -> int:
        return self.__dynamic_id

    async def get_info(self) -> dict:
        """
        获取动态信息

        Returns:
            dict: 调用 API 返回的结果
        """

        api = API["info"]["detail"]
        params = {"dynamic_id": self.__dynamic_id}
        data = await request(
            "GET", api["url"], params=params, credential=self.credential
        )

        data["card"]["card"] = json.loads(data["card"]["card"])
        data["card"]["extend_json"] = json.loads(data["card"]["extend_json"])
        return data["card"]

    async def get_reposts(self, offset: str = "0") -> dict:
        """
        获取动态转发列表

        Args:
            offset (str, optional): 偏移值（下一页的第一个动态 ID，为该请求结果中的 offset 键对应的值），类似单向链表. Defaults to "0"

        Returns:
            dict: 调用 API 返回的结果
        """
        api = API["info"]["repost"]
        params: dict[str, Any] = {"dynamic_id": self.__dynamic_id}
        if offset != "0":
            params["offset"] = offset
        return await request(
            "GET", api["url"], params=params, credential=self.credential
        )

    async def get_likes(self, pn: int = 1, ps: int = 30) -> dict:
        """
        获取动态点赞列表

        Args:
            pn (int, optional): 页码，defaults to 1
            ps (int, optional): 每页大小，defaults to 30

        Returns:
            dict: 调用 API 返回的结果
        """
        api = API["info"]["likes"]
        params = {"dynamic_id": self.__dynamic_id, "pn": pn, "ps": ps}
        return await request(
            "GET", api["url"], params=params, credential=self.credential
        )

    async def set_like(self, status: bool = True) -> dict:
        """
        设置动态点赞状态

        Args:
            status (bool, optional): 点赞状态. Defaults to True.

        Returns:
            dict: 调用 API 返回的结果
        """
        self.credential.raise_for_no_sessdata()
        self.credential.raise_for_no_bili_jct()

        api = API["operate"]["like"]

        user_info = await user.get_self_info(credential=self.credential)

        self_uid = user_info["mid"]
        data = {
            "dynamic_id": self.__dynamic_id,
            "up": 1 if status else 2,
            "uid": self_uid,
        }
        return await request("POST", api["url"], data=data, credential=self.credential)

    async def delete(self) -> dict:
        """
        删除动态

        Returns:
            dict: 调用 API 返回的结果
        """
        self.credential.raise_for_no_sessdata()

        api = API["operate"]["delete"]
        data = {"dynamic_id": self.__dynamic_id}
        return await request("POST", api["url"], data=data, credential=self.credential)

    async def repost(self, text: str = "转发动态") -> dict:
        """
        转发动态

        Args:
            text (str, optional): 转发动态时的文本内容. Defaults to "转发动态"

        Returns:
            dict: 调用 API 返回的结果
        """
        self.credential.raise_for_no_sessdata()

        api = API["operate"]["repost"]
        data = await _get_text_data(text)
        data["dynamic_id"] = self.__dynamic_id
        return await request("POST", api["url"], data=data, credential=self.credential)

class BuildDynmaic:
    def __init__(self) -> None:
        """
        构建动态内容
        """
        self.contents: list = []
        self.pics: list = []
        self.attach_card: Optional[dict] = None
        self.topic: Optional[dict] = None
        self.options: dict = {}

    def add_text(self, text: str) -> "BuildDynmaic":
        """
        添加文本

        Args:
            text (str): 文本内容
        """
        self.contents.append(
            {"biz_id": "", "type": DynmaicContentType.TEXT.value, "raw_text": text})
        return self

    def add_at(self, user: Union[int, User]) -> "BuildDynmaic":
        """
        添加@用户，支持传入 User 类或 UID

        Args:
            user (Union[int, user.User]): UID 或用户类
        """
        if isinstance(user, User):
            user = user.__uid
        self.contents.append(
            {"biz_id": user, "type": DynmaicContentType.EMOJI.value, "raw_text": f"@{user}"})
        return self

    def add_emoji(self, emoji_name: str) -> "BuildDynmaic":
        """
        添加表情

        Args:
            emoji_name (str): 表情名
        """
        self.contents.append({
            "biz_id": "",
            "type": DynmaicContentType.EMOJI.value,
            "raw_text": emoji_name
        }
        )
        return self

    def add_vote(self, vote: Union[Vote, int]) -> "BuildDynmaic":
        """
        添加投票

        Args:
            vote (Union[Vote, int]): 投票类或投票ID
        """
        self.add_text("我发起了一个投票")  # 按照Web端的逻辑，投票动态会自动添加一段文本
        if isinstance(vote, int):
            vote = Vote(vote)
        self.contents.append(
            {"biz_id": str(vote.vote_id), "type": DynmaicContentType.VOTE.value, "raw_text": sync(vote.get_title())}) # vote_id must str
        return self

    def add_image(self, image: Picture) -> "BuildDynmaic":
        """
        添加图片

        Args:
            image (Picture): 图片类
        """
        # 请自行上传为图片类
        self.pics.append({
            "img_src": image.url,
            "img_width": image.width,
            "img_height": image.height
        })
        return self

    def set_attach_card(self, oid: int) -> "BuildDynmaic":
        """
        设置直播预约

        在 live.create_live_reserve 中获取 oid

        Args:
            oid (int): 卡片oid
        """
        self.attach_card = {
            "type": 14,
            "biz_id": oid,
            "reserve_source": 1,  # 疑似0为视频预告但没法验证...
            "reserve_lottery": 0
        }
        return self

    def set_topic(self, topic: Union[Topic, int]) -> "BuildDynmaic":
        """
        设置话题

        Args:
            topic_id (int, Topci): 话题ID 或话题类
        """
        if isinstance(topic, Topic):
            topic = topic.__topic_id
        self.topic = {
            "id": topic
        }
        return self

    def set_options(self, up_choose_comment: bool = False, close_comment: bool = False) -> "BuildDynmaic":
        """
        设置选项

        Args:
            up_choose_comment	(bool): 	精选评论flag
            close_comment	    (bool): 	关闭评论flag
        """
        if up_choose_comment:
            self.options["up_choose_comment"] = 1
        if close_comment:
            self.options["close_comment"] = 1
        return self

    def get_dynamic_type(self) -> SendDynmaicType:
        if len(self.pics) != 0:
            return SendDynmaicType.IMAGE
        return SendDynmaicType.TEXT

    def get_contents(self) -> list:
        return self.contents

    def get_pics(self) -> list:
        return self.pics

    def get_attach_card(self) -> Optional[dict]:
        return self.attach_card

    def get_topic(self) -> Optional[dict]:
        return self.topic

    def get_options(self) -> dict:
        return self.options


async def send_dynamic(
    info: BuildDynmaic,
    credential: Credential,
) -> Dynamic:
    """
    发送动态

    Args:
        info (BuildDynmaic): 动态内容
        credential (Credential): 凭据

    Returns:
        Dynamic: 动态类
    """
    credential.raise_for_no_sessdata()
    api = API["send"]["instant"]
    data = {"dyn_req": {
        "content": {  # 必要参数
            "contents": info.get_contents()
        },
        "scene": info.get_dynamic_type().value,  # 必要参数
        "meta": {
            "app_meta": {
                "from": "create.dynamic.web",
                        "mobi_app": "web"
            },
        }
    }
    }
    if len(info.get_pics()) != 0:
        data["dyn_req"]["pics"] = info.get_pics()
    if info.get_topic() is not None:
        data["dyn_req"]["topic"] = info.get_topic()
    if len(info.get_options()) > 0:
        data["dyn_req"]["option"] = info.get_options()
    if info.get_attach_card() is not None:
        data["dyn_req"]["attach_card"] = {}
        data["dyn_req"]["attach_card"]["common_card"] = info.get_attach_card()
    else:
        data["dyn_req"]["attach_card"] = None
    send_result = await request("POST", api["url"], data=data, credential=credential, params={"csrf": credential.bili_jct}, json_body=True)
    return Dynamic(dynamic_id=send_result["dyn_id"], credential=credential)

# 定时动态操作


async def get_schedules_list(credential: Credential) -> dict:
    """
    获取待发送定时动态列表

    Args:
        credential  (Credential): 凭据

    Returns:
        dict: 调用 API 返回的结果
    """
    credential.raise_for_no_sessdata()

    api = API["schedule"]["list"]
    return await request("GET", api["url"], credential=credential)


async def send_schedule_now(draft_id: int, credential: Credential) -> dict:
    """
    立即发送定时动态

    Args:
        draft_id (int): 定时动态 ID
        credential  (Credential): 凭据

    Returns:
        dict: 调用 API 返回的结果
    """
    credential.raise_for_no_sessdata()

    api = API["schedule"]["publish_now"]
    data = {"draft_id": draft_id}
    return await request("POST", api["url"], data=data, credential=credential)


async def delete_schedule(draft_id: int, credential: Credential) -> dict:
    """
    删除定时动态

    Args:
        draft_id (int): 定时动态 ID
        credential  (Credential): 凭据

    Returns:
        dict: 调用 API 返回的结果
    """
    credential.raise_for_no_sessdata()

    api = API["schedule"]["delete"]
    data = {"draft_id": draft_id}
    return await request("POST", api["url"], data=data, credential=credential)





async def get_new_dynamic_users(credential: Union[Credential, None] = None) -> dict:
    """
    获取更新动态的关注者

    Args:
        credential (Credential | None): 凭据类. Defaults to None.

    Returns:
        dict: 调用 API 返回的结果
    """
    credential = credential if credential else Credential()
    credential.raise_for_no_sessdata()
    api = API["info"]["attention_new_dynamic"]
    return await request("GET", api["url"], credential=credential)


async def get_live_users(size: int = 10, credential: Union[Credential, None] = None) -> dict:
    """
    获取正在直播的关注者

    Args:
        size       (int)       : 获取的数据数量. Defaults to 10.
        credential (Credential | None): 凭据类. Defaults to None.

    Returns:
        dict: 调用 API 返回的结果
    """
    credential = credential if credential else Credential()
    credential.raise_for_no_sessdata()
    api = API["info"]["attention_live"]
    params = {"size": size}
    return await request("GET", api["url"], params=params, credential=credential)


async def get_dynamic_page_UPs_info(credential: Credential) -> dict:
    """
    获取动态页 UP 主列表

    Args:
        credential (Credential): 凭据类.

    Returns:
        dict: 调用 API 返回的结果
    """
    api = API["info"]["dynamic_page_UPs_info"]
    return await request("GET", api["url"], credential=credential)


async def get_dynamic_page_info(credential: Credential, _type: Optional[DynamicType] = None, host_mid: Optional[int] = None, pn: int = 1, offset: Optional[int] = None) -> List[Dynamic]:
    """
    获取动态页动态信息

    获取全部动态或者相应类型需传入 _type
    获取指定 UP 主动态需传入 host_mid

    Args:
        credential (Credential): 凭据类.
        _type      (DynamicType, optional): 动态类型. Defaults to DynamicType.ALL.
        host_mid   (int, optional): 获取对应 UP 主动态的 mid. Defaults to None.
        pn         (int, optional): 页码. Defaults to 1.
        offset     (int, optional): 偏移值（下一页的第一个动态 ID，为该请求结果中的 offset 键对应的值），类似单向链表. Defaults to None.


    Returns:
        list[Dynamic]: 动态类列表
    """

    api = API["info"]["dynamic_page_info"]
    params = {
        "timezone_offset": -480,
        "features": "itemOpusStyle",
        "offset": offset,
        "page": pn,
    }
    if _type:  # 全部动态
        params["type"] = _type.value
    elif host_mid:  # 指定 UP 主动态
        params["host_mid"] = host_mid

    dynmaic_data = await request("GET", api["url"], credential=credential, params=params)
    return [Dynamic(dynamic_id=int(dynamic["id_str"]), credential=credential) for dynamic in dynmaic_data["items"]]
