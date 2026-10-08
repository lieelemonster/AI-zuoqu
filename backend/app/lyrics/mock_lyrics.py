"""离线演示模型的歌词模板：按主题、情绪、风格套用固定句式，只用于没有模型密钥时走通流程。"""

from __future__ import annotations

import json
import re

from app.presets import load_presets
from app.providers.mock import register_mock

THEME_WORDS = {
    "love": ("街角的咖啡店", "晚风", "你的笑"),
    "friendship": ("操场的看台", "汽水", "老朋友"),
    "family": ("厨房的灯光下", "炊烟", "妈妈的手"),
    "campus": ("教室的窗边", "粉笔灰", "白衬衫"),
    "dream": ("凌晨的车站", "星光", "远方"),
    "healing": ("安静的海边", "微风", "晴天"),
    "memory": ("旧相册里面", "黄昏", "老照片"),
    "hometown": ("村口的小路", "稻田", "老槐树"),
    "travel": ("出发的站台", "地图", "山海"),
    "daily": ("楼下的早餐店", "阳光", "小日子"),
}

SONG = {
    "story": ("{t}的{a}", "[主歌]\n那天在{s}\n你轻轻说起{t}\n我们走过很多路\n把{a}装进口袋\n"
                          "[副歌]\n{e}的{t}啊\n陪我走到很远\n就算时间会改变\n我也会记得{b}"),
    "emotion": ("{e}的心", "[主歌]\n心里有一点{e}\n说不出口的话\n在夜里慢慢长大\n像{a}一样温柔\n"
                         "[副歌]\n这就是我的{t}\n{e}又真实\n每一次想起你\n心跳都会加速"),
    "imagery": ("{b}与{a}", "[主歌]\n{a}吹过窗前\n光落在旧窗台\n云朵慢慢地飘\n时间轻轻停下来\n"
                           "[副歌]\n{b}在远方闪烁\n照亮{t}的路\n一首歌一段梦\n都写进{a}里"),
}

RAP = {
    "story": ("{t}的{a}", "[主歌]\n走过{s}我想起从前\n那些关于{t}的画面在眼前\n不管路有多远我都不会改变\n"
                          "把{e}的心情写成诗篇\n[副歌]\n这是我的{t}\n{e}在心里\n跟着节拍唱\n一直不放弃"),
    "emotion": ("{e}节拍", "[主歌]\n今天的心情有一点{e}\n说不出的话全都藏在心里面\n跟着鼓点一句一句往前推\n"
                         "不再犹豫这一次我要大声说\n[副歌]\n这是我的{t}\n{e}在心里\n跟着节拍唱\n一直不放弃"),
    "imagery": ("{b}与{a}", "[主歌]\n{a}吹过城市的屋顶\n霓虹闪烁像是一场梦境\n脚步踩着节拍穿过人群\n"
                           "{b}在前方照亮我的心\n[副歌]\n这是我的{t}\n{e}在心里\n跟着节拍唱\n一直不放弃"),
}


def _info(user: str) -> dict[str, str]:
    match = re.search(r"创作信息（JSON）：(\{.*?\})\n", user)
    return json.loads(match.group(1)) if match else {}


@register_mock("lyrics")
def mock_lyrics(system: str, user: str) -> object:
    info = _info(user)
    presets = load_presets()
    theme_id = next((o.id for o in presets.themes if o.name == info.get("主题")), "daily")
    rap = info.get("音乐风格") == next(o.name for o in presets.styles if o.id == "rap")
    scene, first, second = THEME_WORDS.get(theme_id, THEME_WORDS["daily"])
    words = dict(t=info.get("主题", "生活"), e=info.get("情绪", "温暖"), s=scene, a=first, b=second)
    templates = RAP if rap else SONG
    return {"variants": [
        {"approach": approach, "title": title.format(**words), "text": text.format(**words)}
        for approach, (title, text) in templates.items()
    ]}
