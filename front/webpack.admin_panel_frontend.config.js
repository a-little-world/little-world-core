const path = require('path');
const webpack = require('webpack');
const BundleTracker = require('webpack-bundle-tracker');
const CompressionPlugin = require('compression-webpack-plugin');
const CopyPlugin = require('copy-webpack-plugin');

var config = function (env) {
  var publicPath = '/static/dist/admin_panel_frontend/';
  var devTool = env.DEV_TOOL == 'none' ? false : env.DEV_TOOL;
  if (env.PUBLIC_PATH && env.PUBLIC_PATH !== '')
    publicPath = env.PUBLIC_PATH + publicPath;
  // It is always assumed that the backend is mounted at /back
  var outputPath = '../back/static/dist/admin_panel_frontend';
  var entry = './apps/admin_panel_frontend';
  var entryPoint = `${entry}/src/index.js`;
  var debug = env.DEBUG === '1';

  return {
    context: __dirname,
    entry: {
      staticfiles: entryPoint,
    },
    resolve: {
      alias: {
        '@': path.resolve(
          __dirname,
          'apps/admin_panel_frontend/src/'
        ),
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
          './admin_panel_frontend.webpack-stats.json'
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
      //['styled-components', { ssr: false }],
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
          include: [
            path.resolve(__dirname, 'apps/admin_panel_frontend/src'),
          ],
        },
        {
          test: /\.css$/,
          use: ['style-loader', 'css-loader'],
        },
        {
          test: /\.svg$/,
          use: [
            {
              loader: '@svgr/webpack',
            },
            {
              loader: 'file-loader',
            },
          ],
          type: 'javascript/auto',
          issuer: {
            and: [/\.(ts|tsx|js|jsx|md|mdx)$/],
          },
        },
        {
          test: /\.(png|jpg|gif|ttf)$/,
          use: {
            loader: 'file-loader',
            options: {
              name: '[name].[hash:8].[ext]',
            },
          },
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
