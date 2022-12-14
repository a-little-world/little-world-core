const path = require('path');
const webpack = require('webpack');
const BundleTracker = require('webpack-bundle-tracker');
const CompressionPlugin = require('compression-webpack-plugin');
const CopyPlugin = require('copy-webpack-plugin');

var config = function (env) {
  var publicPath = '/static/dist/user_form_frontend/';
  var devTool = env.DEV_TOOL == 'none' ? false : env.DEV_TOOL;
  if (env.PUBLIC_PATH && env.PUBLIC_PATH !== '')
    publicPath = env.PUBLIC_PATH + publicPath;
  // It is always assumed that the backend is mounted at /back
  var outputPath = '../back/static/dist/user_form_frontend';
  var entry = './apps/user_form_frontend';
  var entryPoint = `${entry}/src/index.tsx`;
  var debug = env.DEBUG === '1';

  return {
    context: __dirname,
    entry: {
      staticfiles: entryPoint,
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'apps/user_form_frontend/src/'),
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
          './user_form_frontend.webpack-stats.json'
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
            extensions: [
              '.js',
              '.jsx',
              '.ts',
              '.tsx',
              '.js',
              '.json',
            ],
          },
          include: [
            path.resolve(__dirname, 'apps/user_form_frontend/src'),
          ],
        },
        {
          test: /\.svg$/,
          issuer: /\.(jsx|tsx)$/,
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
          test: /\.(png|jpg|gif|ttf)$/,
          use: {
            loader: 'file-loader',
            options: {
              name: '[name].[hash:8].[ext]',
            },
          },
        },
        {
          test: /\.css$/,
          use: ['style-loader', 'css-loader', 'postcss-loader'],
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
