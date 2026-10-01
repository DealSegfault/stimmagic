import base64

import pytest

from tests.helpers.media import create_media_item


@pytest.mark.parametrize('file_format', ['html', 'htm', 'stimmalayout', 'png'])
async def test_html_preview_formats_and_local_reference_boundary(client, db_session, tmp_path, file_format):
    bundle = tmp_path / 'bundle'
    bundle.mkdir()
    local_image = b'local image bytes'
    (bundle / 'reference.png').write_bytes(local_image)
    (tmp_path / 'outside.png').write_bytes(b'outside file must not be embedded')
    (bundle / 'escape.png').symlink_to(tmp_path / 'outside.png')
    path = bundle / ('index.html' if file_format == 'stimmalayout' else f'storyboard.{file_format}')
    path.write_text(
        '<!doctype html><h1>Storyboard preview</h1>'
        '<img src="reference.png"><img src="../outside.png"><img src="escape.png">',
        encoding='utf-8',
    )
    async with db_session() as session:
        media = await create_media_item(
            session, file_path=bundle if file_format == 'stimmalayout' else path,
            file_format=file_format,
        )
        await session.commit()
    response = await client.get(f'/api/media/{media.id}/layout-html')
    if file_format == 'png':
        assert response.status_code == 400
        return
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/html')
    assert '<h1>Storyboard preview</h1>' in response.text
    assert f'data:image/png;base64,{base64.b64encode(local_image).decode()}' in response.text
    assert 'src="../outside.png"' in response.text
    assert 'src="escape.png"' in response.text
    assert base64.b64encode(b'outside file must not be embedded').decode() not in response.text
