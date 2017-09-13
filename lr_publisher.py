import glob
import os
from pprint import pprint
import re
import sqlite3
import shutil
import sys


DEFAULT_CATALOG = os.path.join(os.getenv('HOME'), 'Pictures', 'Lightroom', 'Catalog', 'Catalog.lrcat')
DEFAULT_SRC = os.path.join(os.getenv('HOME'), 'Pictures', 'Full Size Pictures')
DEFAULT_DST = os.path.join(os.getenv('HOME'), 'Amazon Drive', 'Pictures')


def open_catalog():
    catalog = DEFAULT_CATALOG
    if sys.argv[1:]:
        catalog = sys.argv[1]
    db_conn = sqlite3.connect(catalog)
    db = db_conn.cursor()
    db.row_factory = sqlite3.Row
    return db


DB = open_catalog()


def get_destination():
    dest = DEFAULT_DST
    if sys.argv[3:]:
        dest = sys.argv[3]
    return dest


def get_source():
    src = DEFAULT_SRC
    if sys.argv[2:]:
        src = sys.argv[2]
    return src


def get_folders():
    folders = {}
    query = "select * from AgLibraryFolder join AgLibraryRootFolder on AgLibraryFolder.rootFolder = AgLibraryRootFolder.id_local"
    rsp = DB.execute(query)
    for tmp in rsp:
        if tmp['pathFromRoot']:
            folders[tmp['id_local']] = tmp['pathFromRoot']
    return folders


def get_collections():
    collections_query = DB.execute('select * from AgLibraryCollection where systemOnly == 0 order by genealogy')

    collection_sets = {}
    collections = {}

    for cxn in collections_query:
        if cxn['creationId'] == 'com.adobe.ag.library.group':
            path = cxn['genealogy']
            cmps = path.split('/')
            if len(cmps) == 2:
                # root level collection/set
                collection_sets[path] = cxn['name']
            else:
                parent_path = "/".join(cmps[:-1])
                parent_name = collection_sets[parent_path]
                current_name = parent_name + "/" + cxn['name']
                collection_sets[path] = current_name
        elif cxn['creationId'] == 'com.adobe.ag.library.collection':
            path = cxn['genealogy']
            cmps = path.split('/')
            parent_path = "/".join(cmps[:-1])
            if parent_path:
                parent_name = collection_sets[parent_path]
                current_name = parent_name + "/" + cxn['name']
            else:
                current_name = cxn['name']
            collection_id = cxn['id_local']
            collections[collection_id] = {'name': current_name}
    return collections


def is_image_on_top_of_stack(collection_id, image_id):
    # check if image is in stack, if so on top of the stack
    is_in_stack_query = DB.execute('select * from AgLibraryCollectionStackImage where collection=? and image=?', (collection_id, image_id))
    rsp = is_in_stack_query.fetchall()
    if len(rsp) == 0:
        # not in stack, so its considered top
        return True
    # in stack, so check if position is 1
    rsp = rsp[0]
    if rsp['position'] == 1:
        return True
    return False


def get_images_in_collection(collections, folders, collection_ids=None):
    if collection_ids is None:
        collection_ids = collections.keys()

    for collection_id in collection_ids:
        collections[collection_id]['images'] = []
        collections[collection_id]['image_ids'] = []
        collections[collection_id]['id'] = collection_id
        image_query = DB.execute('select image from AgLibraryCollectionImage where collection=?', (collection_id,))
        for img in list(image_query):
            image_id = img['image']
            collections[collection_id]['image_ids'].append(image_id)
            # check if this image is in a stack, if so on position 1
            if not is_image_on_top_of_stack(collection_id, image_id):
                continue
            root_file_query = DB.execute('select rootFile from Adobe_images where id_local=?', (image_id,))
            root_file_data = root_file_query.fetchone()
            root_file_id = root_file_data['rootFile']
            lib_file_query = DB.execute('select * from AgLibraryFile where id_local=?', (root_file_id,))
            image_info = lib_file_query.fetchone()
            folder_id = image_info['folder']
            base_name = image_info['baseName']
            image_path = folders[folder_id] + base_name
            tmp_image_path = image_path
            idx = 0
            while tmp_image_path in collections[collection_id]['images']:
                idx += 1
                tmp_image_path = image_path + '-' + str(idx)
            image_path = tmp_image_path

            collections[collection_id]['images'].append(image_path)
        collections[collection_id]['count'] = len(collections[collection_id]['images'])

    return collections


def publish_images(collections, source, destination, name=None):
    for cxn_id in collections:
        if name and collections[cxn_id]['name'] != name:
            continue
        #pprint(collections[cxn_id])
        dst_collection_folder = os.path.join(destination, collections[cxn_id]['name'])
        try:
            os.makedirs(dst_collection_folder)
        except Exception as e:
            pass
        print 'Publishing', collections[cxn_id]['name']
        added_images = []
        for image in collections[cxn_id]['images']:
            src_image = os.path.join(source, image + '.jpg')
            # because of the suffixes added, the src_image may not exist. so replace the index correctly
            if not os.path.exists(src_image):
                match = re.search('-([0-9]).jpg', src_image)
                if match:
                    suffix = int(match.group(1))
                    while True:
                        if suffix > 100:
                            break
                        new_src_image = src_image.replace(match.group(0), '-%d.jpg' % suffix)
                        if os.path.exists(new_src_image):
                            src_image = new_src_image
                            break
                        else:
                            suffix += 1
            tail_name = os.path.split(src_image)[-1]
            dst_image = os.path.join(dst_collection_folder, tail_name)
            added_images.append(tail_name)
            # if src_image is newer than dst_image, copy
            if not os.path.exists(dst_image) or os.path.getmtime(src_image) > os.path.getmtime(dst_image):
                print "  ", src_image, dst_image
                shutil.copy2(src_image, dst_image)
                #os.symlink(src_image, dst_image)
        delete_extra_images(added_images, dst_collection_folder)
        files = glob.glob(dst_collection_folder + "/*.jpg")
        collections[cxn_id]['images_published'] = len(files)


def delete_extra_folders(collections, destination):
    # delete extra folders in the destination that are not in collections
    dest_folders = []
    for path, child_folders, child_files in os.walk(destination):
        path = path.replace(destination, "").lstrip("/")
        for fldr in child_folders:
            dest_folders.append(os.path.join(path, fldr))
    col_folders = [];
    for cx in collections:
        path = collections[cx]['name']
        col_folders.append(path)
        # add the top level folders into the col_folders as safe folder
        # collections has only the paths to the leaves
        parent = ""
        for tmp_cmp in os.path.split(path)[:-1]:
            if parent:
                parent = os.path.join(parent, tmp_cmp)
            else:
                parent = tmp_cmp
        if parent not in col_folders:
            col_folders.append(parent)
    print "Extra folders to delete"
    for fldr in dest_folders:
        if fldr not in col_folders:
            fldr = os.path.join(destination, fldr)
            print '  ', fldr
            shutil.rmtree(fldr)



def delete_extra_images(image_list, destination_folder):
    children = os.listdir(destination_folder)
    print("Extra Images to delete")
    for child in children:
        if child not in image_list:
            child = os.path.join(destination_folder, child)
            print "  ", child
            os.unlink(child)


def print_summary(collections):
    print "%40s %10s %10s" % ("Name", "Lightroom", "Folder")
    print "-"*80
    lr_count = 0
    folder_count = 0
    for cxn_id in sorted(collections, key=lambda x: collections[x]['name']):
        print "%40s %10d %10d" % (collections[cxn_id]['name'].replace('My Collections/', ''),
                collections[cxn_id]['count'],
                collections[cxn_id]['images_published'])
        lr_count += collections[cxn_id]['count']
        folder_count += collections[cxn_id]['images_published']
    print "-"*80
    print "%40s %10d %10d" % ('Total', lr_count, folder_count)
    print "-"*80

if __name__ == "__main__":
    folders = get_folders()
    collections = get_collections()
    get_images_in_collection(collections, folders)
    src = get_source()
    dst = get_destination()
    publish_images(collections, src, dst)
    delete_extra_folders(collections, dst)
    DB.close()
    print_summary(collections)
