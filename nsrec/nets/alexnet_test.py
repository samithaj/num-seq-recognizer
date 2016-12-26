import tensorflow as tf
from nsrec.nets import alexnet

class AlexnetTest(tf.test.TestCase):

  def test_variable_scope(self):
    with self.test_session():
      inputs = tf.constant(1)
      with alexnet.variable_scope(inputs) as variable_scope:
        self.assertEqual(variable_scope.name, 'alexnet_v2')
        v = tf.get_variable('test', [1])
        self.assertIs(v.graph, inputs.graph)

  def test_variable_scope_with_array(self):
    with self.test_session():
      inputs = tf.constant(1)
      with alexnet.variable_scope([inputs]) as variable_scope:
        self.assertEqual(variable_scope.name, 'alexnet_v2')
        v = tf.get_variable('test', [1])
        self.assertIs(v.graph, inputs.graph)

  def test_cnn_layers_end_points(self):
    batch_size, height, width, channels = 5, 224, 224, 3
    with self.test_session():
      inputs = tf.random_uniform((batch_size, height, width, channels))
      with alexnet.variable_scope([inputs]) as variable_scope:
        end_points_collection = alexnet.end_points_collection_name(variable_scope)
        _, end_points = alexnet.cnn_layers(inputs, variable_scope, end_points_collection)

      expected_names = [
        'alexnet_v2/conv1',
        'alexnet_v2/pool1',
        'alexnet_v2/conv2',
        'alexnet_v2/pool2',
        'alexnet_v2/conv3',
        'alexnet_v2/conv4',
        'alexnet_v2/conv5',
        'alexnet_v2/pool5',
      ]
      self.assertSetEqual(set(end_points.keys()), set(expected_names))

  def test_fc_layers_end_points(self):
    layers_name_prefix = "length"
    batch_size, height, width, channels = 5, 224, 224, 3
    with self.test_session():
      inputs = tf.random_uniform((batch_size, height, width, channels))
      with alexnet.variable_scope([inputs]) as variable_scope:
        end_points_collection = alexnet.end_points_collection_name(variable_scope)
        net, _ = alexnet.cnn_layers(inputs, variable_scope, end_points_collection)
        _, end_points = alexnet.fc_layers(net, variable_scope, end_points_collection, num_classes=10, name_prefix=layers_name_prefix)

      expected_names = [
        'alexnet_v2/%s_fc6' % layers_name_prefix,
        'alexnet_v2/%s_fc7' % layers_name_prefix,
        'alexnet_v2/%s_fc8' % layers_name_prefix
      ]
      self.assertSetEqual(set(filter(lambda x: x.find('_fc') != -1, end_points.keys())),
                          set(expected_names))

  def _checkOutputs(self, expected_shapes, feed_dict=None):
    """Verifies that the model produces expected outputs.

    Args:
      expected_shapes: A dict mapping Tensor or Tensor name to expected output
        shape.
      feed_dict: Values of Tensors to feed into Session.run().
    """
    fetches = list(expected_shapes.keys())

    with self.test_session() as sess:
      sess.run(tf.global_variables_initializer())
      outputs = sess.run(fetches, feed_dict)

    for index, output in enumerate(outputs):
      tensor = fetches[index]
      expected = expected_shapes[tensor]
      actual = output.shape
      if expected != actual:
        self.fail("Tensor %s has shape %s (expected %s)." %
                  (tensor, actual, expected))

  def test_network_output(self):
    batch_size, height, width, channels = 5, 224, 224, 3
    with self.test_session():
      inputs = tf.random_uniform((batch_size, height, width, channels))
      with alexnet.variable_scope([inputs]) as variable_scope:
        end_points_collection = alexnet.end_points_collection_name(variable_scope)
        net, _ = alexnet.cnn_layers(inputs, variable_scope, end_points_collection)
        output, _ = alexnet.fc_layers(net, variable_scope, end_points_collection, num_classes=10)

        self._checkOutputs({
          output: (5, 10),
        })


if __name__ == '__main__':
  tf.test.main()
