import errno
import os
from unittest.mock import Mock, call

import pytest
from transmissionrpc import Torrent

from plexpost import post_processor, htpc_switch, default_flow
from plexpost.sftp_factory import SFTPFactory


@pytest.fixture
def automator(transmission, sftpserver, remote_base_dir, download_dir):
    return post_processor.PostProcessor(transmission,
                                        Mock(),
                                        SFTPFactory({'url': sftpserver.host,
                                                     'port': sftpserver.port,
                                                     'username': 'user',
                                                     'password': '',
                                                     'remote_dir': remote_base_dir}),
                                        default_flow.DefaultPostProcessor({'download_dir_tag': download_dir}))


def test_should_only_remove_torrents_when_they_are_completed(automator, transmission, download_dir):
    torrents = [create_torrent(1, 0, download_dir),
                create_torrent(2, 1, download_dir),
                create_torrent(3, 0, download_dir)]
    transmission.get_torrents.return_value = torrents
    automator.run()
    transmission.remove_torrent.assert_has_calls([call(1), call(3)], any_order=True)


def test_should_wake_htpc_when_torrent_is_complete(completed_torrents, automator, requests, download_dir):
    torrents = [create_torrent(1, 0, download_dir)]
    completed_torrents.return_value = torrents
    automator.htpc = htpc_switch.HTPCSwitch('127.0.0.1', '123123', 'htpc')
    automator.run()
    requests.post.assert_called_with('http://127.0.0.1:8123/api/services/switch/turn_on',
                                     json={'entity_id': 'switch.htpc'},
                                     headers={'Authorization': 'Bearer 123123'})


def test_should_not_wake_htpc_when_no_torrents_complete(completed_torrents, automator, requests):
    completed_torrents.return_value = []
    automator.run()
    requests.post.assert_not_called()


@pytest.mark.parametrize('download_dir', ['tmp/cleanup_top_level_files_when_download_is_complete'])
def test_should_cleanup_top_level_files_when_download_is_complete(completed_torrents, automator, download_dir):
    top_level_file = 'top_level.txt'
    completed_torrents.return_value = [completed_torrent_with_data_files(download_dir, [top_level_file])]
    automator.run()
    assert os.path.isdir(download_dir)
    assert not os.path.isfile(download_dir + '/' + top_level_file)


@pytest.mark.parametrize('download_dir', ['tmp/cleanup_directory_when_download_is_complete'])
def test_should_cleanup_directory_when_download_is_complete(completed_torrents, automator, download_dir):
    file1 = 'dir1/dir2/file'
    file2 = 'dir1/dir2/dir3/file'
    completed_torrents.return_value = [completed_torrent_with_data_files(download_dir, [file1, file2])]
    automator.run()
    assert os.path.isdir(download_dir)
    assert not os.path.lexists(download_dir + '/' + file1)
    assert not os.path.lexists(download_dir + '/' + file2)
    assert not os.path.lexists(download_dir + '/dir1/dir2')
    assert not os.path.lexists(download_dir + '/dir1')


@pytest.mark.parametrize('download_dir', ['tmp/only_cleanup_empty_directories'])
def test_should_only_cleanup_empty_directories(completed_torrents, automator, download_dir):
    torrent_file = 'dir1/dir2/torrent_file'
    external_file = 'dir1/external_file'
    touch(download_dir, external_file)
    completed_torrents.return_value = [completed_torrent_with_data_files(download_dir, [torrent_file])]
    automator.run()
    assert os.path.isfile(download_dir + '/' + external_file)
    assert not os.path.isdir(download_dir + '/dir1/dir2')


@pytest.mark.parametrize('download_dir', ['tmp/copy_top_level_files_to_htpc'])
def test_should_copy_top_level_files_to_htpc(completed_torrents, automator, sftpclient, remote_base_dir, download_dir):
    single_file = 'single_file'
    completed_torrents.return_value = [completed_torrent_with_data_files(download_dir, [single_file])]
    automator.run()
    assert sftpclient.isfile(remote_base_dir + '/downloads/' + single_file)


@pytest.mark.parametrize('download_dir', ['tmp/copy_files_in_directories_to_htpc'])
def test_should_copy_files_in_directories_to_htpc(completed_torrents, automator, sftpclient, remote_base_dir,
                                                  download_dir):
    nested_file = 'dir1/dir2/nested_file'
    completed_torrents.return_value = [completed_torrent_with_data_files(download_dir, [nested_file])]
    automator.run()
    assert sftpclient.isdir(remote_base_dir + '/downloads/dir1/dir2')
    assert sftpclient.isfile(remote_base_dir + '/downloads/' + nested_file)


@pytest.mark.parametrize('download_dir', ['tmp/ignore_missing_files_in_torrent'])
def test_should_ignore_missing_files_in_torrent(completed_torrents, automator, download_dir):
    tor = Mock()
    tor.progress = 100
    tor.id = 1
    tor.downloadDir = download_dir
    tor.name = 'Mock 1'
    data_files = {'0': {'selected': True, 'priority': 'normal', 'size': 1, 'name': download_dir + '/dir/missing_file',
                        'completed': 1}}
    tor.files.return_value = data_files
    completed_torrents.return_value = [tor]
    automator.run()
    assert not os.path.lexists(download_dir + '/dir/missing_file')
    assert not os.path.lexists(download_dir + '/dir')


def create_torrent(id, size_left, download_dir):
    name = 'Torrent ' + str(id)
    fields = {'id': id, 'name': name, 'sizeWhenDone': 1, 'leftUntilDone': size_left, 'downloadDir': download_dir}
    return Torrent(None, fields)


def completed_torrent_with_data_files(prefix, files):
    tor = Mock()
    tor.progress = 100
    tor.id = 1
    tor.downloadDir = prefix
    tor.name = 'Mock 1'
    data_files = {}
    for idx, f in enumerate(files):
        data_files[idx] = create_download_file(prefix, f)
    tor.files.return_value = data_files
    return tor


def create_download_file(prefix, filename):
    return {'selected': True, 'priority': 'normal', 'size': 1, 'name': touch(prefix, filename), 'completed': 1}


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
