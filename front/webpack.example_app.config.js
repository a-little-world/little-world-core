const path = require('path');
const webpack = require('webpack');
const BundleTracker = require('webpack-bundle-tracker');
const CompressionPlugin = require('compression-webpack-plugin');
const CopyPlugin = require('copy-webpack-plugin');

var config = function (env) {
  var publicPath = '/static/dist/example_app/';
  var devTool = env.DEV_TOOL;
  //var outputPath = './dist/example_app';
  // It is always assumed that the backend is mounted at /back
  var outputPath = '../back/static/dist/example_app';
  var entry = './apps/example_app';
  var entryPoint = `${entry}/src/index.js`;
  var debug = env.DEBUG === '1';

  return {
    context: __dirname,
    entry: {
      staticfiles: entryPoint,
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'apps/example_app/src/'),
        '@django': path.resolve(__dirname, '../back/static/'),
      },
    },
    output: {
      path: path.join(__dirname, outputPath),
      filename: '[name]-[hash].js',
      publicPath: publicPath,
    },

    plugins: [
      new BundleTracker({
        filename: path.join(
          __dirname,
          './example_app.webpack-stats.json'
        ),
      }),
      new CompressionPlugin(),
      new CopyPlugin({
        patterns: [
          {
            from: path.resolve(__dirname, `${entry}/public`),
            to: path.join(__dirname, outputPath),
          },
        ],
      }),
    ],
    devtool: devTool,
    module: {
      rules: [
        {
          test: /\.(js|jsx|tsx|ts)$/,
          exclude: /node_modules/,
          use: ['babel-loader'],
          resolve: {
            extensions: ['.js', '.jsx'],
          },
          include: [path.resolve(__dirname, 'apps/example_app/src')],
        },
        {
          test: /\.svg$/,
          use: [
            'babel-loader',
            {
              loader: 'react-svg-loader',
              options: {
                svgo: {
                  plugins: [{ removeTitle: false }],
                  floatPrecision: 2,
                },
                jsx: true,
              },
            },
          ],
        },
        {
          test: /\.(ttf|png|jpg|gif)$/,
          use: {
            loader: 'file-loader',
            options: {
              name: '[name].[hash:8].[ext]',
            },
          },
        },
        {
          test: /\.css$/,
          use: ['style-loader', 'css-loader'],
        },
      ],
    },
  };
};

module.exports = (env, argv) => {
  const conf = config(env);
  console.log(conf);
  return conf;
};
