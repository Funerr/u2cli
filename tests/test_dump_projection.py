from __future__ import annotations

from u2cli.screen.dump import compact_projection


def test_compact_projection_filters_and_preserves_depth() -> None:
    xml = """
    <hierarchy>
      <node text="" class="android.widget.FrameLayout" bounds="[0,0][10,10]" clickable="false" enabled="true">
        <node text="Login" resource-id="com.example:id/login" class="android.widget.Button" bounds="[1,2][3,4]" clickable="true" enabled="true" />
      </node>
    </hierarchy>
    """

    data = compact_projection(xml, {"displayWidth": 1080, "displayHeight": 2400})

    assert data["screenSize"] == [1080, 2400]
    assert data["nodes"] == [
        {
            "id": 0,
            "cls": "Button",
            "text": "Login",
            "desc": None,
            "rid": "com.example:id/login",
            "bounds": [1, 2, 3, 4],
            "clickable": True,
            "enabled": True,
            "checked": False,
            "selected": False,
            "depth": 2,
            "parent": None,
        }
    ]


def test_text_truncation() -> None:
    xml = f'<hierarchy><node text="{"x" * 201}" class="TextView" enabled="true" /></hierarchy>'

    data = compact_projection(xml)

    assert len(data["nodes"][0]["text"]) == 200
    assert data["nodes"][0]["textTruncated"] is True
