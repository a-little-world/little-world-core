const path = require('path');
const webpack = require('webpack');
const BundleTracker = require('webpack-bundle-tracker');
const CompressionPlugin = require('compression-webpack-plugin');
const CopyPlugin = require('copy-webpack-plugin');

var config = function (env) {
  var publicPath = '/static/dist/main_frontend/';
  var devTool = env.DEV_TOOL == 'none' ? false : env.DEV_TOOL;
  // It is always assumed that the backend is mounted at /back
  if (env.PUBLIC_PATH && env.PUBLIC_PATH !== '')
    publicPath = env.PUBLIC_PATH + publicPath;
  var outputPath = '../back/static/dist/main_frontend';
  var entry = './apps/main_frontend';
  var entryPoint = `${entry}/src/index.js`;
  var debug = env.DEBUG === '1';

  return {
    context: __dirname,
    entry: {
      staticfiles: entryPoint,
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'apps/main_frontend/src/'),
        '@django': path.resolve(__dirname, '../back/static/'),
      },
      fallback: { 'process/browser': require.resolve('process/browser'), }
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
          './main_frontend.webpack-stats.json'
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
      new webpack.ProvidePlugin({
        process: 'process/browser',
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
            extensions: ['.js', '.jsx', '.ts', '.tsx'],
          },
          include: [
            path.resolve(__dirname, 'apps/main_frontend/src'),
          ],
        },
        {
          test: /\.(jpg|png|svg|webp|gif|tff)$/,
          type: 'asset/resource',
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