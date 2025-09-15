import React from 'react';
import PropTypes from 'prop-types';
import Icon from './Icon';

class Pagination extends React.Component {
  static defaultProps = {
    currentPage: 1,
    pageSize: 10,
    pageRangeDisplayed: 3,
    marginPagesDisplayed: 1,
    showFirst: true,
    showLast: true,
    showPrevious: false,
    showNext: false,
    // Fill the gap of max size `gapSize` formed by boundary elements
    // of margin pages and main range with buttons instead of showing
    // ellipsis ("..." looks ugly and unnecessary between "1" and "3")
    gapSize: 1,
    force: false
  };

  shouldComponentUpdate(nextProps, nextState, snapshot) {
    return this.props.currentPage !== nextProps.currentPage || this.props.force;
  }

  createPageItem(index, label, currentPage) {
    return (
      <li
        key={index}
        className={`${currentPage === index + 1 ? ' active' : ''}`}
      >
        <button onClick={() => this.setPage(index + 1)}>{label}</button>
      </li>
    );
  }

  createEllipsis(index) {
    return (
      <li key={index} className={`disabled`}>
        <button disabled className="ellipsis">
          &hellip;
        </button>
      </li>
    );
  }

  setPage(page) {
    if (page !== this.props.currentPage) {
      this.props.onChangePage(page);
    }
  }

  getPager() {
    const items = [];
    const { pageRangeDisplayed, marginPagesDisplayed, currentPage, gapSize } =
      this.props;

    let totalPages = this.getTotalPages();
    if (totalPages <= pageRangeDisplayed + marginPagesDisplayed + gapSize) {
      for (let index = 0; index < totalPages; index++) {
        items.push(this.createPageItem(index, index + 1, currentPage));
      }
    } else {
      let leftSide = Math.floor((pageRangeDisplayed - 1) / 2);
      let rightSide = pageRangeDisplayed - leftSide - 1;

      if (currentPage < pageRangeDisplayed) {
        leftSide = currentPage;
        rightSide = pageRangeDisplayed - leftSide;
      } else if (currentPage > totalPages - rightSide) {
        rightSide = totalPages - currentPage;
        leftSide = pageRangeDisplayed - rightSide - 1;
      }
      // Show button instead of ellipsis if gap between margin and
      // range elements <= gapSize
      if (currentPage - leftSide - marginPagesDisplayed - 1 <= gapSize) {
        leftSide += gapSize;
      } else if (
        totalPages - (currentPage + rightSide + marginPagesDisplayed) <=
        gapSize
      ) {
        rightSide += gapSize;
      }

      let ellipsis;
      // Note: Not sure we can reach performance penalty since it needs
      // thousands of page items to iterate. If you care, skip
      // indexes after inserting ellipsis
      for (let index = 0; index < totalPages; index++) {
        let page = index + 1;
        if (page <= marginPagesDisplayed) {
          items.push(this.createPageItem(index, page, currentPage));
          continue;
        }

        if (page >= currentPage - leftSide && page <= currentPage + rightSide) {
          items.push(this.createPageItem(index, page, currentPage));
          continue;
        }

        if (page > totalPages - marginPagesDisplayed) {
          items.push(this.createPageItem(index, page, currentPage));
          continue;
        }

        if (items[items.length - 1] !== ellipsis) {
          ellipsis = this.createEllipsis(index);
          items.push(ellipsis);
        }
      }
    }

    return items;
  }
  getTotalPages() {
    return Math.ceil(this.props.totalItems / this.props.pageSize);
  }

  render() {
    let pager = this.getPager();
    let currentPage = this.props.currentPage;
    let totalPages = this.getTotalPages();
    if (!pager || pager.length <= 1) {
      // don't display pager if there is only 1 page
      return null;
    }

    return (
      <ul className="pagination">
        {totalPages > 5 && currentPage !== 1 && (
          <li>
            <button onClick={() => this.setPage(1)}>
              <Icon id="fa-angle-double-left" />
            </button>
          </li>
        )}

        {pager}

        {totalPages > 5 && currentPage !== totalPages && (
          <li>
            <button onClick={() => this.setPage(totalPages)}>
              <Icon id="fa-angle-double-right" />
            </button>
          </li>
        )}
      </ul>
    );
  }
}

Pagination.propTypes = {
  force: PropTypes.bool, // force to re-render component
  gapSize: PropTypes.number.isRequired,
  pageSize: PropTypes.number.isRequired,
  onChangePage: PropTypes.func.isRequired,
  pageRangeDisplayed: PropTypes.number.isRequired,
  marginPagesDisplayed: PropTypes.number.isRequired,
  currentPage: PropTypes.number,
  totalItems: PropTypes.number.isRequired
};

export default Pagination;
