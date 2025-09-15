const path = require('path');

const TerserPlugin = require('terser-webpack-plugin');
const webpack = require('webpack');
const BundleTracker = require('webpack-bundle-tracker');

const APP_VERSION = process.env.APP_VERSION || 'v1';
const LOCAL_BUILD = process.env.LOCAL_BUILD === '1';
const DEBUG = process.env.DEBUG === '1';
const BUILD_DIR = LOCAL_BUILD ? 'local' : 'prod';

let __outputdir = path.join(
  __dirname,
  `../assets/${APP_VERSION}/dist/${BUILD_DIR}`
);

// TODO: add css minimization
const config = {
  mode: 'production',

  devtool: LOCAL_BUILD ? 'source-map' : false,

  output: {
    clean: true,
    path: __outputdir,
    filename: '[name]-[contenthash].js',
    chunkFilename: '[name].[contenthash].js',
    publicPath: `/static/${APP_VERSION}/dist/${BUILD_DIR}/`,
    assetModuleFilename: ({ filename }) => {
      // Keeps file structure to the asset file
      const absPathToFile = path.resolve(filename);
      const nodeModulesDir = path.join(
        path.dirname(absPathToFile).split('node_modules')[0],
        'node_modules'
      );
      // relative to the module
      const filepath = path.dirname(
        path.relative(nodeModulesDir, absPathToFile)
      );
      return `assets/${filepath}/[hash][ext][query]`;
    }
  },

  stats: {
    errorDetails: true,
    hash: true,
    timings: true,
    assets: true,
    chunks: true,
    chunkModules: true,
    modules: true,
    children: true
  },

  optimization: {
    runtimeChunk: 'single',
    moduleIds: 'deterministic',
    concatenateModules: true,
    minimize: !DEBUG,
    minimizer: [
      new TerserPlugin({
        minify: TerserPlugin.swcMinify,
        extractComments: true, // extract licenses into separate file
      })
    ]
  },

  plugins: [
    new webpack.DefinePlugin({
      'process.env.NODE_ENV': JSON.stringify('production')
    }),
    new BundleTracker({
      path: __outputdir,
      filename: `webpack-stats-${APP_VERSION}.json`,
      relativePath: true
    })
  ]
};

module.exports = config;
