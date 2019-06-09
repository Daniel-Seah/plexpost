import errno
import os
from unittest.mock import Mock, call, patch

from transmissionrpc import Torrent

import default_flow


@patch('default_flow.requests')
@patch('default_flow.transmission')
def test_should_remove_torrent_when_they_are_completed(transmission, r):
    tc = Mock()
    tc.get_torrents.return_value = [Torrent(None, {'id': 1, 'sizeWhenDone': 1, 'leftUntilDone': 0}),
                                    Torrent(None, {'id': 2, 'sizeWhenDone': 1, 'leftUntilDone': 1}),
                                    Torrent(None, {'id': 3, 'sizeWhenDone': 2, 'leftUntilDone': 0})]
    transmission.Client.return_value = tc
    proc = default_flow.DefaultPostProcessor(url='localhost', port=9091, username='user', password='password')

    proc.run()

    tc.remove_torrent.assert_has_calls([call(1), call(3)], any_order=True)


@patch('default_flow.requests')
@patch('default_flow.transmission')
def test_should_wake_htpc_when_torrent_is_complete(transmission, request):
    tc = Mock()
    tc.get_torrents.return_value = [Torrent(None, {'id': 1, 'sizeWhenDone': 1, 'leftUntilDone': 0})]
    transmission.Client.return_value = tc
    proc = default_flow.DefaultPostProcessor(assistant_url='127.0.0.1',
                                             assistant_token='123123',
                                             htpc_switch='htpc')

    proc.run()

    request.post.assert_called_with('http://127.0.0.1:8123/api/services/switch/turn_on',
                                    json={'entity_id': 'switch.htpc'},
                                    headers={'Authorization': 'Bearer 123123'})


@patch('default_flow.requests')
@patch('default_flow.transmission')
def test_should_cleanup_top_level_files_when_download_is_complete(transmission, r):
    tc = Mock()
    prefix = 'tmp/cleanup_test'
    top_level_file = 'top_level.txt'
    touch(prefix, top_level_file)
    tor = Mock()
    tor.progress = 100
    tor.id = 1
    tor.downloadDir = prefix
    tor.files.return_value = {
        0: {'selected': True, 'priority': 'normal', 'size': 1, 'name': top_level_file,
            'completed': 1}}
    tc.get_torrents.return_value = [tor]
    transmission.Client.return_value = tc

    default_flow.DefaultPostProcessor().run()

    assert os.path.isdir(prefix)
    assert not os.path.isfile(prefix + '/' + top_level_file)


@patch('default_flow.requests')
@patch('default_flow.transmission')
def test_should_cleanup_directory_when_download_is_complete(transmission, r):
    tc = Mock()
    prefix = 'tmp/cleanup_dir_test'
    file1 = 'dir1/file'
    file2 = 'dir1/dir2/file'
    tor = Mock()
    tor.progress = 100
    tor.id = 1
    tor.downloadDir = prefix
    tor.files.return_value = {
        0: {'selected': True, 'priority': 'normal', 'size': 1, 'name': touch(prefix, file1),
            'completed': 1},
        1: {'selected': True, 'priority': 'normal', 'size': 1, 'name': touch(prefix, file2),
            'completed': 1}
    }
    tc.get_torrents.return_value = [tor]
    transmission.Client.return_value = tc

    default_flow.DefaultPostProcessor().run()

    assert os.path.isdir(prefix)
    assert not os.path.isfile(prefix + '/' + file1)
    assert not os.path.isdir(prefix + '/dir1')
    assert not os.path.isfile(prefix + '/' + file2)
    assert not os.path.isdir(prefix + '/dir1/dir2')


@patch('default_flow.requests')
@patch('default_flow.transmission')
def test_should_only_cleanup_empty_directories(transmission, r):
    tc = Mock()
    prefix = 'tmp/cleanup_empty_dir_test'
    torrent_file = 'dir1/dir2/torrent_file'
    tor = Mock()
    tor.progress = 100
    tor.id = 1
    tor.downloadDir = prefix
    tor.files.return_value = {
        0: {'selected': True, 'priority': 'normal', 'size': 1, 'name': touch(prefix, torrent_file),
            'completed': 1}}
    external_file = 'dir1/external_file'
    touch(prefix, external_file)
    tc.get_torrents.return_value = [tor]
    transmission.Client.return_value = tc

    default_flow.DefaultPostProcessor().run()

    assert os.path.isfile(prefix + '/' + external_file)
    assert not os.path.isdir(prefix + '/dir1/dir2')


def touch(prefix, file):
    path = prefix + '/' + file
    if not os.path.exists(os.path.dirname(path)):
        try:
            os.makedirs(os.path.dirname(path))
        except OSError as exc:  # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise
    with open(path, 'a'):
        os.utime(path)
    return file