# lightroom_collection_tree
Mirror the collection/collection sets in Lightroom onto the file system.

# work in progress

This is a python script that runs on the terminal. It mirrors the lightroom collection tree onto the filesystem. However it needs a setup that depends on other plugins

It uses http://regex.info/blog/lightroom-goodies/folder-publisher

Install this plugin and make a folder structure available on the file system. This plugin mirrors the folder structure on lightroom onto the filesystem. The plugin provides options to set the export quality and size.

Once the exported folder structure is available on the file system, this script uses that as the source of images and then mirrors the collection tree.
