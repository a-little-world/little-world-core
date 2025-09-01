const path = require("path");
const webpack = require("webpack");
const BundleTracker = require("webpack-bundle-tracker");
const CompressionPlugin = require("compression-webpack-plugin");
const CopyPlugin = require("copy-webpack-plugin");

var config = function (env) {
  var publicPath = "/static/dist/admin_panel_frontend/";
  var devTool = env.DEV_TOOL == "none" ? false : env.DEV_TOOL;
  // It is always assumed that the backend is mounted at /back
  if (env.PUBLIC_PATH && env.PUBLIC_PATH !== "")
    publicPath = env.PUBLIC_PATH + publicPath;
  var outputPath = "../back/static/dist/admin_panel_frontend";
  var entry = "./apps/admin_panel_frontend";
  var entryPoint = `${entry}/src/index.js`;

  return {
    context: __dirname,
    entry: {
      staticfiles: entryPoint,
    },
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "apps/admin_panel_frontend/src/"),
        "@django": path.resolve(__dirname, "../back/static/"),
        "prettier/standalone": path.resolve(
          __dirname,
          "apps/admin_panel_frontend/node_modules/prettier"
        ),
      },
      fallback: { "process/browser": require.resolve("process/browser") },
    },
    output: {
      path: path.join(__dirname, outputPath),
      filename: "[name]-[hash].js",
      publicPath: publicPath,
    },

    plugins: [
      new BundleTracker({
        filename: path.join(
          __dirname,
          "./admin_panel_frontend.webpack-stats.json"
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
        process: "process/browser",
      }),
      new webpack.DefinePlugin({
        "process.env.NODE_ENV": JSON.stringify(
          env.DEBUG === "1" ? "development" : "production"
        ),
        __DEV__: env.DEBUG === "1",
        "global.__DEV__": env.DEBUG === "1",
        "process.env.BUILD_TYPE": JSON.stringify(
          env.DEBUG === "1" ? "dev" : "pro"
        ),
      }),
    ],
    devtool: devTool,
    module: {
      rules: [
        {
          test: /\.(js|jsx|tsx|ts)$/,
          exclude: /node_modules/,
          use: ["babel-loader"],
          resolve: {
            extensions: [".js", ".jsx", ".ts", ".tsx"],
          },
          include: [path.resolve(__dirname, "apps/admin_panel_frontend/src")],
        },
        {
          test: /\.svg$/,
          use: [
            {
              loader: "@svgr/webpack",
            },
            {
              loader: "file-loader",
            },
          ],
          type: "javascript/auto",
          issuer: {
            and: [/\.(ts|tsx|js|jsx|md|mdx)$/],
          },
        },
        {
          test: /\.(jpg|png|webp|gif|ttf|woff|woff2|eot|otf)$/,
          use: {
            loader: "file-loader",
            options: {
              name: "[name].[hash:8].[ext]",
            },
          },
        },
        {
          test: /\.css$/,
          use: [
            "style-loader",
            "css-loader",
            {
              loader: "postcss-loader",
              options: {
                postcssOptions: {
                  plugins: [
                    require(path.resolve(
                      __dirname,
                      "apps/admin_panel_frontend/node_modules/tailwindcss"
                    ))({
                      config: path.resolve(
                        __dirname,
                        "apps/admin_panel_frontend/tailwind.config.js"
                      ),
                    }),
                    require(path.resolve(
                      __dirname,
                      "apps/admin_panel_frontend/node_modules/autoprefixer"
                    )),
                  ],
                },
              },
            },
          ],
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
