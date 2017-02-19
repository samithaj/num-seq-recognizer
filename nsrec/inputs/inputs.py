import os

import h5py
import numpy as np
from scipy import ndimage, misc
from six.moves import cPickle as pickle

import tensorflow as tf
from nsrec.inputs.models import BBox, Data
from nsrec.utils.np_ops import one_hot


def bbox_batches(data_generator_fn, batch_size, size, num_preprocess_threads=1, is_training=True, channels=3):
  filenames, bboxes, length_labels, numbers_labels = data_generator_fn()
  tf.logging.info('input data count: %s', len(filenames))

  filename_queue = tf.train.string_input_producer(
    filenames, shuffle=False, capacity=batch_size * 3)
  bbox_queue = tf.train.input_producer(
    tf.constant(bboxes, dtype=tf.int32), shuffle=False, element_shape=(4, ), capacity=batch_size * 3)

  reader = tf.WholeFileReader()
  _, dequeued_record_string = reader.read(filename_queue)

  dequeued_data = []
  for i in range(num_preprocess_threads):
    dequeued_img = tf.image.decode_png(dequeued_record_string, channels)
    img_shape = tf.shape(dequeued_img)
    dequeued_img = resize_image(dequeued_img, None, is_training, size, channels)
    bbox = bbox_queue.dequeue()
    normalized_bbox = [bbox[0]/img_shape[1], bbox[1]/img_shape[0], bbox[2]/img_shape[1], bbox[3]/img_shape[0]]
    normalized_bbox = tf.cast(normalized_bbox, tf.float32)
    dequeued_data.append([dequeued_img, normalized_bbox])

  return tf.train.batch_join(
    dequeued_data,
    batch_size=batch_size, capacity=batch_size * 3)


def batches(data_generator_fn, max_number_length, batch_size, size,
            num_preprocess_threads=1, is_training=True, channels=1):
  filenames, bboxes, length_labels, numbers_labels = data_generator_fn()

  tf.logging.info('input data count: %s', len(filenames))

  filename_queue = tf.train.string_input_producer(
    filenames, shuffle=False, capacity=batch_size * 3)
  length_label_queue = tf.train.input_producer(
    tf.constant(length_labels), shuffle=False, element_shape=(max_number_length, ), capacity=batch_size * 3)
  numbers_label_queue = tf.train.input_producer(
    tf.constant(numbers_labels), shuffle=False, element_shape=(max_number_length, 11), capacity=batch_size * 3)
  bbox_queue = tf.train.input_producer(
    tf.constant(bboxes, dtype=tf.int32), shuffle=False, element_shape=(4, ), capacity=batch_size * 3)

  reader = tf.WholeFileReader()
  _, dequeued_record_string = reader.read(filename_queue)

  # TODO: why non-zero size image issue if num_preprocess_threads > 1
  dequeued_data = []
  for i in range(num_preprocess_threads):
    dequeued_img = tf.image.decode_png(dequeued_record_string, channels)
    # dequeued_img = tf.Print(dequeued_img, [_, tf.shape(dequeued_img)], 'dequeued image: ')
    dequeued_img = resize_image(dequeued_img, bbox_queue.dequeue(), is_training, size, channels)
    dequeued_data.append([dequeued_img, length_label_queue.dequeue(), numbers_label_queue.dequeue()])

  return tf.train.batch_join(
    dequeued_data,
    batch_size=batch_size, capacity=batch_size * 3)


def resize_image(dequeued_img, dequeued_bbox, is_training, size, channels=1):
  def image_summary(name, image):
    # tf.summary.image(name, tf.expand_dims(image, 0))
    pass

  # Should be the first one to call, or will cause NaN issue
  dequeued_img = tf.image.convert_image_dtype(dequeued_img, dtype=tf.float32)
  image_summary("original_image", dequeued_img)

  if dequeued_bbox is not None:
    dequeued_img = dequeued_img[
      dequeued_bbox[1]:dequeued_bbox[1]+dequeued_bbox[3], dequeued_bbox[0]:dequeued_bbox[0]+dequeued_bbox[2], :
    ]
    image_summary("bbox_image", dequeued_img)

  # dequeued_img = tf.image.resize_images(dequeued_img, [int(size[0] * 1.5), int(size[1] * 1.5)])
  dequeued_img = tf.image.resize_images(dequeued_img, [size[0], size[1]])
  image_summary("resized_images", dequeued_img)

  # Crop to final dimensions.
  # if is_training:
  #   dequeued_img = tf.random_crop(dequeued_img, [size[0], size[1], channels])
  # else:
  #   # Central crop, assuming resize_height > height, resize_width > width.
  #   dequeued_img = tf.image.resize_image_with_crop_or_pad(dequeued_img, size[0], size[1])
  image_summary("final_image", dequeued_img)

  return dequeued_img


def create_mat_metadata_handler(metadata_file_path, max_number_length, data_dir_path):

  def handler():
    filenames, bboxes, length_labels, numbers_labels = [], [], [], []
    metadata = metadata_generator(metadata_file_path)

    read_count = 0
    for data in metadata:
      read_count += 1
      if len(data.label) > max_number_length:
        tf.logging.info('ignore data since label is too long: filename=%s, label=%s' % (data.filename, data.label))
        continue

      filename, length_label, numbers_label = _to_data(data.filename, data.label, max_number_length, data_dir_path)
      filenames.append(filename)
      length_labels.append(length_label)
      numbers_labels.append(numbers_label)
      bboxes.append(data.bbox())

      if read_count % 1000 == 0:
        tf.logging.info('readed %s records', read_count)

    length_labels_nd = np.ndarray((len(filenames), max_number_length))
    numbers_labels_nd = np.ndarray((len(filenames), max_number_length, 11))

    for i, length_label in enumerate(length_labels):
      length_labels_nd[i, :] = length_label
      numbers_labels_nd[i, :, :] = numbers_labels[i]

    return filenames, bboxes, length_labels_nd, numbers_labels_nd


  return handler


def _to_data(filename, label, max_number_length, data_dir_path):
  # fix label if longer than max_number_length
  label = label[:max_number_length]
  if max_number_length == 1:
    numbers_one_hot = [one_hot(ord(label) - ord('0') + 1, 11)]
  else:
    numbers_one_hot = [one_hot(ord(ch) - ord('0') + 1, 11) for ch in label]
  no_number_one_hot = [one_hot(11, 11) for i in range(max_number_length - len(label))]
  filename = os.path.join(data_dir_path, filename)
  length_label = one_hot(len(label), max_number_length)
  if len(label) < max_number_length:
    numbers_label = np.concatenate([numbers_one_hot, no_number_one_hot])
  else:
    numbers_label = numbers_one_hot
  return filename, length_label, numbers_label


def create_pickle_metadata_handler(metadata_file_path, max_number_length, data_dir_path):

  def handler():
    with open(metadata_file_path, 'rb') as f:
      metadata = pickle.load(f)
    short_filenames, labels, bboxes = metadata['filenames'], metadata['labels'], metadata['bboxes']

    filenames = []
    length_labels = np.ndarray((len(short_filenames), max_number_length))
    numbers_labels = np.ndarray((len(short_filenames), max_number_length, 11))

    for i, filename in enumerate(short_filenames):
      filename, length_label, numbers_label = _to_data(filename, labels[i], max_number_length, data_dir_path)
      length_labels[i,:] = length_label
      numbers_labels[i, :, :] = numbers_label
      filenames.append(filename)

    return filenames, bboxes, length_labels, numbers_labels

  return handler


def metadata_generator(file_path):
  f = h5py.File(file_path)
  refs, ds = f['#refs#'], f['digitStruct']

  def bboxes(i):
    attr_names = 'label top left width height'.split()
    bboxes = []
    bboxes_raw = refs[ds['bbox'][i][0]]
    bboxes_count = bboxes_raw['label'].value.shape[0]
    for j in range(bboxes_count):
      real_value = lambda ref_or_real_value: refs[ref_or_real_value].value.reshape(-1)[0] \
        if isinstance(ref_or_real_value, h5py.h5r.Reference) else ref_or_real_value
      attr_value = lambda attr_name: real_value(bboxes_raw[attr_name].value[j][0])
      bboxes.append(BBox(*[attr_value(an) for an in attr_names]))
    return bboxes

  for i, name in enumerate(ds['name']):
    ords = refs[name[0]].value
    name_str = ''.join([chr(ord) for ord in ords.reshape(-1)])
    yield Data(name_str, bboxes(i))


def mnist_batches(batch_size, size, num_preprocess_threads=1, is_training=True, data_count=55000):
  current_dir = os.path.dirname(os.path.abspath(__file__))
  mnist_data_dir = os.path.join(current_dir, '../../MNIST-data')
  from tensorflow.examples.tutorials.mnist import input_data
  mnist = input_data.read_data_sets(mnist_data_dir, one_hot=True)

  data, label = mnist.train.next_batch(data_count)
  data = data.reshape(data_count, 28, 28, 1)

  data_queue = tf.train.input_producer(data, shuffle=False, element_shape=(28, 28, 1), capacity=batch_size * 3)

  dequeued_image = data_queue.dequeue()
  dequeued_image = resize_image(dequeued_image, None, is_training, size, channels=1)

  label_queue = tf.train.input_producer(label, shuffle=False, element_shape=(10, ), capacity=batch_size * 3)

  return tf.train.batch(
    [dequeued_image, label_queue.dequeue()],
    batch_size=batch_size, capacity=batch_size * 3)


def fix_bbox(image, w, h, bbox, expand_rate=0.1, accept_min_rate=0.05):
  top = max([bbox[1] - h * expand_rate, 0])
  bottom = min([bbox[1] + bbox[3] + h * expand_rate, h])
  left = max([bbox[0] - w * expand_rate, 0])
  right = min([bbox[0] + bbox[2] + w * expand_rate, w])
  if bottom - top < accept_min_rate * h:
    top, bottom = 0, h
  if right - left < accept_min_rate * w:
    left, right = 0, w
  return image[top:bottom, left:right, :]


def read_img(img_file, bbox):
  image = ndimage.imread(img_file)
  if bbox:
    image = fix_bbox(image, image.shape[1], image.shape[0], bbox)
  return image

pixel_depth = 255.0


def normalize_img(image, size):
  image = misc.imresize(image, size).astype(np.float32)
  image = (image- pixel_depth / 2) / pixel_depth
  assert image.shape == (size[0], size[1], 3)
  return image
