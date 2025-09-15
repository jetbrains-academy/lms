const path = require('path')
const MiniCssExtractPlugin = require('mini-css-extract-plugin')

const srcDir = path.join(__dirname, '../src/v1/scss')
const nodeModulesDir = path.join(__dirname, '../node_modules')
let outDir = path.join(__dirname, `../assets/v1/dist/css`)

module.exports = {
  context: srcDir,
  entry: {
    center_staff: path.join(srcDir, '/center/staff.scss'),
    center_style: path.join(srcDir, '/center/style.scss'),
  },
  module: {
    rules: [
      {
        test: /\.s[ac]ss$/,
        exclude: nodeModulesDir,
        use: [
          MiniCssExtractPlugin.loader,
          {
            loader: 'css-loader',
            options: {
              url: {
                filter: (url, resourcePath) => {
                  return resourcePath.includes('@fontsource')
                }
              },
            },
          },
          {
            loader: 'sass-loader',
            options: {
              sassOptions: {
                includePaths: [srcDir]
              }
            }
          },
        ],
      },
    ],
  },
  plugins: [
    new MiniCssExtractPlugin({
      filename: '[name].css',
      chunkFilename: '[name].css',
    }),
  ],
  output: {
    clean: true,
    path: outDir,
    filename: '[name].js',
  },
}
