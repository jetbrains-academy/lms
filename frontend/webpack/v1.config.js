const path = require('path');

const Dotenv = require('dotenv-webpack');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');
const { merge } = require('webpack-merge'); // merge webpack configs

const DEVELOPMENT = process.env.NODE_ENV === 'development';

process.env.BABEL_ENV = process.env.NODE_ENV;

const APP_VERSION = 'v1';

const __srcdir = path.join(__dirname, `../src/${APP_VERSION}`);
const __nodemodulesdir = path.join(__dirname, '../node_modules');

const common = {
  context: __srcdir,

  entry: {
    vendor: [
      path.join(__srcdir, '/js/components/editor'),
    ],
    main: { import: path.join(__srcdir, '/js/main.js'), dependOn: 'vendor' },
    // TODO: use 1 entry
    teaching: {
      import: path.join(__srcdir, '/js/teaching/index.js'),
      dependOn: 'vendor',
    },
    supervising: {
      import: path.join(__srcdir, '/js/supervising/index.js'),
      dependOn: 'vendor',
    },
  },

  externals: {
    // Note: EpicEditor is a dead library.
    EpicEditor: 'EpicEditor',
  },

  resolve: {
    extensions: ['.jsx', '.js', '.tsx', '.ts'],
    modules: [path.join(__srcdir, '/js'), __nodemodulesdir],
    symlinks: false,
    alias: {
      jquery: 'jquery/src/jquery',
      '~': __srcdir,
    },
  },

  module: {
    rules: [
      {
        test: /\.(js|css)$/,
        enforce: "pre",
        use: ["source-map-loader"],
      },
      {
        test: /\.(js|jsx)$/,
        use: [
          {
            loader: 'babel-loader',
          },
        ],
        include: path.resolve(__srcdir, 'js'),
      },
      {
        test: /\.tsx?$/,
        use: 'ts-loader',
        include: path.resolve(__srcdir, 'js'),
      },
      {
        test: /\.s?[ac]ss$/,
        exclude: __nodemodulesdir,
        use: [
          DEVELOPMENT ? 'style-loader' : MiniCssExtractPlugin.loader,
          'css-loader', // translates CSS into CommonJS modules
          {
            loader: 'sass-loader', // compiles SASS to CSS
            options: {
              sassOptions: {
                outputStyle: 'expanded',
                // precision: 8,
                includePaths: [__nodemodulesdir],
              },
            },
          },
        ],
      },
      {
        test: /\.css$/,
        include: __nodemodulesdir,
        use: [
          DEVELOPMENT ? 'style-loader' : MiniCssExtractPlugin.loader,
          'css-loader',
        ],
      },
      {
        // Serve static in node_modules/
        test: /\.woff2?$|\.ttf$|\.eot$|\.svg$|\.png$|\.jpg$|\.swf$/,
        include: __nodemodulesdir,
        type: 'asset/resource',
        generator: {
          emit: !DEVELOPMENT,
        },
      },
    ],
  },

  plugins: [
    new Dotenv({
      path: path.join(__dirname, '.env'),
      silent: true,
    }),
    new MiniCssExtractPlugin({
      // Options similar to the same options in webpackOptions.output
      // both options are optional
      filename: DEVELOPMENT ? '[name].css' : '[name].[hash].css',
      chunkFilename: DEVELOPMENT
        ? '[id].[name].css'
        : '[name]-[contenthash].css',
    }),
  ],

  optimization: {
    splitChunks: {
      minChunks: 2,
      cacheGroups: {
        vendor: {
          name: 'vendor',
          test: 'vendor',
          enforce: true,
        },
        forms: {
          name: 'forms',
          test: 'components/forms',
          enforce: true,
        },
      },
    },
  },
};

let appConfig;
if (DEVELOPMENT) {
  appConfig = merge(common, require('./dev.config'));
} else {
  appConfig = merge(common, require('./prod.config'));
}

module.exports = appConfig;
